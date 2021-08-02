#!/usr/bin/env python
import dataclasses
from datetime import datetime
from datetime import timedelta
from math import ceil
from pathlib import Path
from typing import Dict, List, Tuple

from exif import Image
import fire
import gpxpy
from gpxpy.gpx import GPXTrackPoint
from gpxpy.gpxfield import SimpleTZ

GPXData = Dict[datetime, Tuple[GPXTrackPoint, Path]]


def compute_gpx_stats(gpx_points: GPXData, stats_file: Path) -> None:
    pass


@dataclasses.dataclass
class GPSDateTime:
    timestamp: Tuple[float, float, float]
    datestamp: str


def datetime_to_exif(dt: datetime, tz_adjust: int = 0) -> GPSDateTime:
    """
    >>> datetime_to_exif(datetime(2021, 8, 2, 15, 19, 17), -2)
    GPSDateTime(timestamp=(13.0, 19.0, 17.0), datestamp='2021:08:02')

    I can see following:
    * IN: 2021:08:02 15:19:17
    * OUT:
        gps_timestamp = (13.0, 19.0, 10.0)
        gps_datestamp = 2021:08:02
    """
    return GPSDateTime(
        timestamp=(1.0 * (dt.hour + tz_adjust), 1.0 * dt.minute, 1.0 * dt.second),
        datestamp=f"{dt.year}:{dt.month:02d}:{dt.day:02d}",
    )


def gpx_to_exif(c: float) -> Tuple[float, float, float]:
    """
    # >>> gpx_to_exif(15.0)
    # (15.0, 0.0, 0.0)
    # >>> gpx_to_exif(15.0 + 30.0 / 60.0)
    # (15.0, 30.0, 0.0)
    >>> gpx_to_exif(15.0 + 30.0 / 60.0 + 30.0 / 3600.0)
    (15.0, 30.0, 30.0)

    >>> gpx_to_exif(-15.0)
    (-15.0, 0.0, 0.0)
    >>> gpx_to_exif(-15.0 - 30.0 / 60.0)
    (-15.0, 30.0, 0.0)
    >>> gpx_to_exif(-15.0 - 30.0 / 60.0 - 30.0 / 3600.0)
    (-15.0, 30.0, 30.0)

    :param c:
    :return:
    """
    a = abs(c)
    h = int(a)
    m = int(60 * (a - h))
    s = ceil(3600 * (a - (h + m / 60.0)))

    return (a / c) * h, 1.0 * m, 1.0 * s


def interpolate(
    before: GPXTrackPoint, after: GPXTrackPoint, dt: datetime
) -> GPXTrackPoint:
    """
    >>> interpolate(\
      GPXTrackPoint(latitude=10.0, longitude=10.0, time=datetime(2021, 8, 2, 10)), \
      GPXTrackPoint(latitude=11.0, longitude=11.0, time=datetime(2021, 8, 2, 11)), \
      datetime(2021, 8, 2, 10, 30) \
    )
    GPXTrackPoint(10.5, 10.5, time=datetime.datetime(2021, 8, 2, 10, 30))

    >>> interpolate(\
      GPXTrackPoint(latitude=10.0, longitude=10.0, time=datetime(2021, 8, 2, 10)), \
      GPXTrackPoint(latitude=11.0, longitude=11.0, time=datetime(2021, 8, 2, 11)), \
      datetime(2021, 8, 2, 10, 15) \
    )
    GPXTrackPoint(10.25, 10.25, time=datetime.datetime(2021, 8, 2, 10, 15))

    :param before:
    :param after:
    :param dt:
    :return:
    """

    # print(f"{before.time=}")
    # print(f"{before.time!r}")
    # print(f"{dt=}")
    # print(f"{after.time=}")

    assert before.time <= dt <= after.time, f"{before=} <= {dt=} <= {after=}"

    if before == after:
        return before

    ratio = 1.0 * (dt - before.time).seconds / (after.time - before.time).seconds

    return GPXTrackPoint(
        latitude=before.latitude + ratio * (after.latitude - before.latitude),
        longitude=before.longitude + ratio * (after.longitude - before.longitude),
        elevation=(
            (before.elevation + ratio * (after.elevation - before.elevation))
            if before.elevation
            else None
        ),
        time=dt,
        symbol=before.symbol,
        comment=before.comment,
        horizontal_dilution=before.horizontal_dilution,
        vertical_dilution=before.vertical_dilution,
        position_dilution=before.position_dilution,
        speed=before.speed,
        name=before.name,
    )


def adjust_image(img: Image, point: GPXTrackPoint):
    """
    Adjust image with GPS coordinates from GPXTrackPoint
    :param img:
    :param point:
    :return:
    """

    """
    Format:
        gps_version_id = 2
        gps_latitude_ref = N
        gps_latitude = (50.0, 6.0, 17.0)
        gps_longitude_ref = E
        gps_longitude = (14.0, 23.0, 36.0)
        gps_altitude_ref = 0
        gps_altitude = 257.0
        gps_timestamp = (13.0, 19.0, 10.0)
        gps_datestamp = 2021:08:02
    """
    img.set("gps_version_id", 2)
    img.set("gps_latitude_ref", "N" if point.latitude > 0 else "S")
    img.set("gps_latitude", gpx_to_exif(point.latitude))
    img.set("gps_longitude_ref", "E" if point.longitude > 0 else "W")
    img.set("gps_longitude", gpx_to_exif(point.longitude))
    img.set("gps_altitude_ref", 0 if point.elevation > 0 else -1)
    img.set("gps_altitude", point.elevation)
    ts = datetime_to_exif(point.time)
    img.set("gps_timestamp", ts.timestamp)
    img.set("gps_datestamp", ts.datestamp)


def adjust_main(
    gpx_dir: str,
    img_dir: str,
    stats_file: str = "",
    gpx_suffix: str = "gpx",
    img_suffix: str = "jpg",
    timezone_adjustment: int = -2,
) -> None:
    print(f"{gpx_dir=}; {img_dir=}; {stats_file=}")

    # load available GPX files
    gpx_points = {}  # type: GPXData
    used_dts = []  # type: List[datetime]
    for gpx_file in sorted(Path(gpx_dir).glob(f"*.{gpx_suffix}")):
        print(f"Processing GPX File {gpx_file}")
        with open(gpx_file) as gpx_fh:
            gpx = gpxpy.parse(gpx_fh)
            for track in gpx.tracks:
                for segment in track.segments:
                    for point in segment.points:
                        gpx_points[point.time] = (point, gpx_file)
                        used_dts.append(point.time)

    print(f"GPX: {len(gpx_points)=}")

    if stats_file:
        compute_gpx_stats(gpx_points, Path(stats_file))

    sorted(used_dts)

    for img_file in sorted(Path(img_dir).glob(f"*.{img_suffix}")):
        print(f"Processing Image File {img_file}")
        img = None
        error = False
        with open(img_file, "rb") as img_fh:
            img = Image(img_fh)
            print(f"{img_file=} => {img.exif_version}")
            # print(img.list_all())
            parts = img.get("datetime_digitized", "").split(" ")
            d_p = parts[0].split(":")
            t_p = parts[1].split(":")
            exif_dt = (
                datetime(
                    int(d_p[0]),
                    int(d_p[1]),
                    int(d_p[2]),
                    int(t_p[0]),
                    int(t_p[1]),
                    int(t_p[2]),
                    tzinfo=SimpleTZ("Z"),
                )
                + timedelta(hours=timezone_adjustment)
            )
            before = None
            after = None
            for u in used_dts:
                if u <= exif_dt:
                    before = u
                if u >= exif_dt:
                    after = u
                    break

            if before is None or after is None:
                print(f"{img_file} - skipping")
                continue

            print(f"DT: {exif_dt=}; B: {before=}; A: {after=}")
            try:
                adjust_image(
                    img,
                    interpolate(gpx_points[before][0], gpx_points[after][0], exif_dt),
                )
            except RuntimeError as e:
                print(f"{img_file} - ERROR - {e}")
                error = True

        if not error:
            with open(img_file, "wb") as img_fh_w:
                assert img is not None
                img_fh_w.write(img.get_file())


if __name__ == "__main__":
    fire.Fire(adjust_main)
