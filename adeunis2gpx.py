#!/usr/bin/python3
#
# adeunis2gpx - A converter for Adeunis LoRaWAN FTD logs to GPX
# Copyright (c) 2021-09-10 13:02:05 Antonio Eugenio Burriel <aeburriel@gmail.com>

from argparse import ArgumentParser, FileType
from collections import namedtuple
from datetime import date, datetime, time
from gpxpy import gpx
from typing import Optional, TextIO
from xml.etree.ElementTree import Element, SubElement
import sys

NTAdeunisSample = namedtuple("AdeunisSample",
    ("time, latitude, longitude, "
     "uSF, uFrequency, uPower, uSNR, uQ, "
     "dSF, dFrequency, dRSSI, dSNR, dQ, "
     "ul, dl, per"))


class AdeunisSample(NTAdeunisSample):
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

    def toGPX(self, day: date) -> str:
        out = gpx.GPX()
        out.creator = "adeunis2gpx"

        for sample in self.samples:
            if not (sample.latitude or sample.longitude):
                continue

            timestamp = datetime.combine(day, sample.time) if sample.time else None
            uSF = f"SF{sample.uSF}" if sample.uSF else "-"
            dSF = f"SF{sample.dSF}" if sample.dSF else "-"
            uSNR = f"{sample.uSNR:+}㏈" if sample.uSNR else "-"
            dSNR = f"{sample.dSNR:+}㏈" if sample.dSNR else "-"
            uFrequency = f"{sample.uFrequency / 1e6}MHz" if sample.uFrequency else "-"
            dFrequency = f"{sample.dFrequency / 1e6}MHz" if sample.dFrequency else "-"
            uPower = f"{sample.uPower:+}㏈m" if sample.uPower else "-"
            dRSSI = f"{sample.dRSSI:+}㏈m" if sample.dRSSI else "-"
            uQ = sample.uQ if sample.uQ else "-"
            dQ = sample.dQ if sample.dQ else "-"
            nameD = f"↓{dRSSI}﹫{dSNR}" if sample.dRSSI else None
            nameU = f"↑{uSNR}" if sample.uSNR else None
            name = " ".join(filter(None, (nameD,nameU)))
            if not name:
                name = "∅"
            description = (
                f"Uplink:   {uSF} @ {uFrequency}, Power: {uPower}, SNR: {uSNR}, Q: {uQ}\n"
                f"Downlink: {dSF} @ {dFrequency}, RSSI: {dRSSI}, SNR: {dSNR}, Q: {dQ}\n"
                f"Counters: Upload: {sample.ul}, Download: {sample.dl}, PER: {sample.per}%"
                )
            point = gpx.GPXTrackPoint(sample.latitude, sample.longitude,
                time=timestamp, name=name)
            point.description = description
            point.extensions.append(sample.toXML("lora", "TrackPointExtension"))
            out.waypoints.append(point)

        return out.to_xml()


def namePrefix(tag: str, namespace: Optional[str] = None) -> str:
    # https://stackoverflow.com/questions/51295158/avoiding-none-in-f-string
    return ":".join(filter(None, (namespace, tag)))


def dms2dd(degrees: float, minutes: float, seconds: float, direction: str) -> float:
    # https://stackoverflow.com/questions/33997361/how-to-convert-degree-minute-second-to-degree-decimal
    dd = degrees + minutes / 60 + seconds / (60 * 60)
    if direction == "S" or direction == "W":
        return -dd
    return dd


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
    parser.add_argument("-o", "--output", nargs="?", type=FileType("w"), default=sys.stdout,
        help="specify the output file.  The default is stdout")
    args = parser.parse_args()

    adeunis = AdeunisLog()
    for file in args.infile:
        with file as f:
            adeunis.parse(f)

    with args.output as f:
        f.write(adeunis.toGPX(args.date))
