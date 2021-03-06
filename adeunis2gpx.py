#!/usr/bin/python3
#
# adeunis2gpx - A converter for Adeunis LoRaWAN FTD logs to GPX
# Copyright (c) 2021-09-10 13:02:05 Antonio Eugenio Burriel <aeburriel@gmail.com>

from argparse import ArgumentParser, FileType
from collections import namedtuple
from datetime import date, datetime, time
from geojson import dumps, Feature, Point, FeatureCollection
from gpxpy import gpx
from io import StringIO
from typing import Optional, TextIO
from xml.etree.ElementTree import Element, SubElement

import csv
import sys


NTAdeunisSample = namedtuple("AdeunisSample",
    ("time, latitude, longitude, "
     "uSF, uFrequency, uPower, uSNR, uQ, "
     "dSF, dFrequency, dRSSI, dSNR, dQ, "
     "ul, dl, per"))


class AdeunisSample(NTAdeunisSample):
    def toGeoJSON(self, day: date) -> Feature:
        timestamp = datetime.combine(day, self.time)
        data = {
                "timestamp": str(timestamp),
                "ul": self.ul,
                "dl": self.dl,
                "PER": self.per
            }

        if self.uSF:
            data["uSF"] = self.uSF
        if self.uFrequency:
            data["uFrequency"] = self.uFrequency
        if self.uPower:
            data["uPower"] = self.uPower
        if self.uSNR:
            data["uSNR"] = self.uSNR
        if self.uQ:
            data["uQ"] = self.uQ

        if self.dFrequency:
            if self.dSF:
                data["dSF"] = self.dSF
            if self.dFrequency:
                data["dFrequency"] = self.dFrequency
            if self.dRSSI:
                data["dRSSI"] = self.dRSSI
            if self.dSNR:
                data["dSNR"] = self.dSNR
            if self.dQ:
                data["dQ"] = self.dQ

        return Feature(geometry=Point((self.longitude, self.latitude)), properties=data)

    def toXML(self, namespace: str, rootTag: str) -> Element:
        root = Element(namePrefix(rootTag, namespace), {namePrefix(namespace, "xmlns"): "http://www.example.org/adeunis2gpx"})

        uplink = SubElement(root, namePrefix("uplink", namespace))
        if self.uSF:
            SubElement(uplink, namePrefix("spreading-factor", namespace)).text = f"{self.uSF}"
        if self.uFrequency:
            SubElement(uplink, namePrefix("frequency", namespace)).text = f"{self.uFrequency}"
        if self.uPower:
            SubElement(uplink, namePrefix("power", namespace)).text = f"{self.uPower:+}"
        if self.uSNR:
            SubElement(uplink, namePrefix("SNR", namespace)).text = f"{self.uSNR:+}"
        if self.uQ:
            SubElement(uplink, namePrefix("quality", namespace)).text = f"{self.uQ}"

        if self.dFrequency:
            downlink = SubElement(root, namePrefix("downlink", namespace))
            if self.dSF:
                SubElement(downlink, namePrefix("spreading-factor", namespace)).text = f"{self.dSF}"
            if self.dFrequency:
                SubElement(downlink, namePrefix("frequency", namespace)).text = f"{self.dFrequency}"
            if self.dRSSI:
                SubElement(downlink, namePrefix("RSSI", namespace)).text = f"{self.dRSSI:+}"
            if self.dSNR:
                SubElement(downlink, namePrefix("SNR", namespace)).text = f"{self.dSNR:+}"
            if self.dQ:
                SubElement(downlink, namePrefix("quality", namespace)).text = f"{self.dQ}"

        counters = SubElement(root, namePrefix("counters", namespace))
        SubElement(counters, namePrefix("sent", namespace)).text = f"{self.ul}"
        SubElement(counters, namePrefix("received", namespace)).text = f"{self.dl}"
        SubElement(counters, namePrefix("error-rate", namespace)).text = f"{self.per}%"

        return root


class AdeunisLog:
    Q_SYMBOL_MISSING = "Navaid, Black"
    Q_SYMBOL_UNKNOWN = "Navaid, White"
    Q_SYMBOLS = {
        0: "Navaid, Red",
        1: "Navaid, Orange",
        2: "Navaid, Amber",
        3: "Navaid, Green",
    }

    def __init__(self):
        self.samples = []

    def parse(self, log: TextIO):
        while line := log.readline():
            fields = line.split()
            if len(fields) != 22:
                continue

            try:
                lat = dms2dd(float(fields[1]), float(fields[2]), float(fields[3]), fields[4])
            except ValueError:
                lat = None
            try:
                lon = dms2dd(float(fields[5]), float(fields[6]), float(fields[7]), fields[8])
            except ValueError:
                lon = None

            sample = AdeunisSample(parseTime(fields[0]), lat, lon,
                parseSF(fields[9]), parseFrequency(fields[10]), parsePower(fields[11]), parseDB(fields[12]), parseQ(fields[13]),
                parseSF(fields[14]), parseFrequency(fields[15]), parsePower(fields[16]), parseDB(fields[17]), parseQ(fields[18]),
                int(fields[19]), int(fields[20]), parsePercent(fields[21]))
            self.samples.append(sample)

    def toCSV(self, day: date) -> str:
        output = StringIO()
        fields = (
            "timestamp", "latitude", "longitude",
            "uSF", "uFrequency", "uPower", "uSNR", "uQ",
            "dSF", "dFrequency", "dRSSI", "dSNR", "dQ",
            "ul", "dl", "PER"
        )
        writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)
        writer.writerow(fields)

        for sample in self.samples:
            if not (sample.latitude or sample.longitude):
                continue

            timestamp = datetime.combine(day, sample.time) if sample.time else None
            writer.writerow((
                timestamp, sample.latitude, sample.longitude,
                sample.uSF, sample.uFrequency, sample.uPower, sample.uSNR, sample.uQ,
                sample.dSF, sample.dFrequency, sample.dRSSI, sample.dSNR, sample.dQ,
                sample.ul, sample.dl, sample.per
            ))
        return output.getvalue()

    def toGeoJSON(self, day: date) -> str:
        features = []
        for sample in self.samples:
            if not (sample.latitude or sample.longitude):
                continue
            features.append(sample.toGeoJSON(day))

        collection = FeatureCollection(features)
        return dumps(collection)

    def toGPX(self, day: date, markers: str) -> str:
        out = gpx.GPX()
        out.creator = "adeunis2gpx"

        for sample in self.samples:
            if not (sample.latitude or sample.longitude):
                continue

            timestamp = datetime.combine(day, sample.time) if sample.time else None
            uSF = f"SF{sample.uSF}" if sample.uSF else "-"
            dSF = f"SF{sample.dSF}" if sample.dSF else "-"
            uSNR = f"{sample.uSNR:+}???" if sample.uSNR else "-"
            dSNR = f"{sample.dSNR:+}???" if sample.dSNR else "-"
            uFrequency = f"{sample.uFrequency / 1e6}MHz" if sample.uFrequency else "-"
            dFrequency = f"{sample.dFrequency / 1e6}MHz" if sample.dFrequency else "-"
            uPower = f"{sample.uPower:+}???m" if sample.uPower else "-"
            dRSSI = f"{sample.dRSSI:+}???m" if sample.dRSSI else "-"
            uQ = sample.uQ if sample.uQ else "-"
            dQ = sample.dQ if sample.dQ else "-"

            nameD = f"???{dRSSI}???{dSNR}" if sample.dRSSI else None
            nameU = f"???{uSNR}" if sample.uSNR else None
            name = " ".join(filter(None, (nameD, nameU)))
            if not name:
                name = "???"
            description = (
                f"Uplink:   {uSF} @ {uFrequency}, Power: {uPower}, SNR: {uSNR}, Q: {uQ}\n"
                f"Downlink: {dSF} @ {dFrequency}, RSSI: {dRSSI}, SNR: {dSNR}, Q: {dQ}\n"
                f"Counters: Upload: {sample.ul}, Download: {sample.dl}, PER: {sample.per}%"
                )

            if markers == "cross":
                symbol = "Crossing"
            else:
                symbol = self.Q_SYMBOL_MISSING
                if markers == "downlink" and sample.dQ:
                    symbol = self.Q_SYMBOLS.get(sample.dQ, self.Q_SYMBOL_UNKNOWN)
                elif markers == "uplink" and sample.uQ:
                    symbol = self.Q_SYMBOLS.get(sample.uQ, self.Q_SYMBOL_UNKNOWN)

            point = gpx.GPXTrackPoint(sample.latitude, sample.longitude,
                time=timestamp, name=name, symbol=symbol)
            point.description = description
            point.extensions.append(sample.toXML("lora", "TrackPointExtension"))
            point.source = "Adeunis LoRaWAN Field Test Device"
            point.type = "field sample"
            out.waypoints.append(point)

        return out.to_xml()


def dms2dd(degrees: float, minutes: float, seconds: float, direction: str) -> float:
    # https://stackoverflow.com/questions/33997361/how-to-convert-degree-minute-second-to-degree-decimal
    dd = degrees + minutes / 60 + seconds / (60 * 60)
    if direction == "S" or direction == "W":
        return -dd
    return dd


def namePrefix(tag: str, namespace: Optional[str] = None) -> str:
    # https://stackoverflow.com/questions/51295158/avoiding-none-in-f-string
    return ":".join(filter(None, (namespace, tag)))


def parseDB(text: str) -> int:
    try:
        return int(text.strip("dB"))
    except ValueError:
        return None


def parseFrequency(text: str) -> int:
    try:
        return int(text.strip("kHz")) * 1000
    except ValueError:
        return None


def parsePercent(text: str) -> int:
    try:
        return int(text.strip("%"))
    except ValueError:
        return None


def parsePower(text: str) -> int:
    try:
        return int(text.strip("dBm"))
    except ValueError:
        return None


def parseQ(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        return None


def parseSF(text: str) -> str:
    try:
        return int(text.strip("SF"))
    except ValueError:
        return None


def parseText(text: str) -> str:
    if text == len(text) * text[0]:
        return None
    return text


def parseTime(text: str) -> time:
    try:
        return time.fromisoformat(text)
    except ValueError:
        return None


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("infile", nargs="+", type=FileType("r"),
        help="specify input files")
    parser.add_argument("-d", "--date", nargs="?", type=date.fromisoformat, default=date.today(),
        help="specify the mandatory date for GPX timestamps in ISO 8601 format.  The default is today's date")
    parser.add_argument("-m", "--markers", nargs="?", choices=["cross", "downlink", "uplink"], default="cross",
        help="specify the marker for the samples.  The default is 'cross'. 'downlink' and 'uplink' represents received and transmitted signal strength respectively")
    parser.add_argument("-o", "--output", nargs="?", type=FileType("w"), default=sys.stdout,
        help="specify the output file.  The default is stdout")
    parser.add_argument("-t", "--type", nargs="?", choices=["csv", "geojson", "gpx"], default="gpx",
        help="specify the output format.  The default is 'gpx'.")
    args = parser.parse_args()

    adeunis = AdeunisLog()
    for file in args.infile:
        with file as f:
            adeunis.parse(f)

    with args.output as f:
        if args.type == "csv":
            output = adeunis.toCSV(args.date)
        elif args.type == "geojson":
            output = adeunis.toGeoJSON(args.date)
        elif args.type == "gpx":
            output = adeunis.toGPX(args.date, args.markers)
        f.write(output)
