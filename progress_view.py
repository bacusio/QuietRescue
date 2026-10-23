"""Read-only helpers for the rescue progress band."""
import json
from pathlib import Path

STATE_COLORS = {
    'saved': '#32965c',
    'reported_saved': '#3388bb',
    'unconfirmed': '#9361b4',
    'error': '#c74c4c',
    'skipped': '#8f959b',
    'unknown': '#d3d3d3',
}


def load_progress(path):
    with Path(path).open('r', encoding='utf-8-sig') as stream:
        data = json.load(stream)
    if data.get('schema') != 'disk-rescue-progress/v1':
        raise ValueError('不支援的進度檔格式')
    source = data.get('source') or {}
    capacity = int(source.get('size_bytes') or 0)
    if capacity <= 0 or not source.get('serial'):
        raise ValueError('進度檔缺少來源序號或有效容量')
    ranges = data.get('ranges')
    if not isinstance(ranges, list):
        raise ValueError('進度檔缺少範圍清單')
    for item in ranges:
        start, end = int(item['start']), int(item['end'])
        if start < 0 or end <= start or end > capacity:
            raise ValueError('進度範圍超出來源容量')
        if item.get('state') not in STATE_COLORS:
            raise ValueError(f"未知進度狀態：{item.get('state')}")
    return data


def matches_device(data, serial, size_bytes):
    source = data.get('source') or {}
    serial = str(serial or '').strip()
    source_serial = str(source.get('serial') or '').strip()
    try:
        source_size = int(source.get('size_bytes') or 0)
        size_bytes = int(size_bytes or 0)
    except (TypeError, ValueError):
        return False
    return bool(serial and source_serial and serial.casefold() == source_serial.casefold()
                and source_size > 0 and source_size == size_bytes)


def slider_byte_for_x(x, width, capacity, sector=512, end=None):
    capacity = int(capacity)
    width = int(width)
    if capacity <= 0 or width <= 20:
        return 0
    x = max(10.0, min(width - 10.0, float(x)))
    value = int(((x - 10.0) / (width - 20.0)) * capacity)
    value = (value // int(sector)) * int(sector)
    if end is not None and int(end) > 0:
        maximum = max(0, ((int(end) - int(sector)) // int(sector)) * int(sector))
        value = min(value, maximum)
    return max(0, min(capacity, value))
