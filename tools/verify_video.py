# -*- coding: utf-8 -*-
"""录制件验收：时长、分辨率、编码、实际帧率、卡顿检测、音轨是否疑似静音。

不依赖 ffmpeg，直接解析 MP4 的 moov（mvhd / tkhd / stsd / stts / stsz）。

判读口径：
- 实际帧率 = 视频样本数 / 时长。明显低于 30 就算丢帧。
- 最大帧间隔来自 stts（解码时间增量），>0.4 秒说明画面卡了一下。
- 音频平均码率 = 音频样本总字节 * 8 / 时长。AAC 语音通常 >40kbps；
  持续低于 8kbps 基本可以判定为静音轨。
"""
from __future__ import annotations

import struct
import sys

CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"dinf", b"udta"}


def boxes(data, start, end):
    pos = start
    while pos + 8 <= end:
        size = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        hdr = 8
        if size == 1:
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            hdr = 16
        elif size == 0:
            size = end - pos
        if size < hdr:
            break
        yield typ, pos + hdr, pos + size
        pos += size


def find(data, start, end, path):
    want = path[0]
    for typ, ps, pe in boxes(data, start, end):
        if typ == want:
            if len(path) == 1:
                return ps, pe
            if typ in CONTAINERS:
                r = find(data, ps, pe, path[1:])
                if r:
                    return r
    return None


def parse(path):
    data = open(path, "rb").read()
    out = {"file_size": len(data)}
    moov = find(data, 0, len(data), [b"moov"])
    if not moov:
        out["error"] = "找不到 moov"
        return out

    mvhd = find(data, moov[0], moov[1], [b"mvhd"])
    if mvhd:
        p = mvhd[0]
        ver = data[p]
        if ver == 1:
            ts = struct.unpack(">I", data[p + 20:p + 24])[0]
            dur = struct.unpack(">Q", data[p + 24:p + 32])[0]
        else:
            ts = struct.unpack(">I", data[p + 12:p + 16])[0]
            dur = struct.unpack(">I", data[p + 16:p + 20])[0]
        out["duration_s"] = dur / ts if ts else None

    tracks = []
    for typ, ts_, te in boxes(data, moov[0], moov[1]):
        if typ != b"trak":
            continue
        info = {"type": "other"}
        hdlr = find(data, ts_, te, [b"mdia", b"hdlr"])
        if hdlr:
            h = data[hdlr[0] + 8:hdlr[0] + 12]
            info["type"] = {b"vide": "video", b"soun": "audio"}.get(h, "other")
        tkhd = find(data, ts_, te, [b"tkhd"])
        if tkhd:
            p = tkhd[0]
            off = p + (88 if data[p] == 1 else 76)
            w = struct.unpack(">I", data[off:off + 4])[0] / 65536.0
            h = struct.unpack(">I", data[off + 4:off + 8])[0] / 65536.0
            if w and h:
                info["width"], info["height"] = int(round(w)), int(round(h))
        stsd = find(data, ts_, te, [b"mdia", b"minf", b"stbl", b"stsd"])
        if stsd:
            info["codec"] = data[stsd[0] + 12:stsd[0] + 16].decode("latin1", "ignore")

        # 样本数
        stsz = find(data, ts_, te, [b"mdia", b"minf", b"stbl", b"stsz"])
        if stsz:
            p = stsz[0]
            sample_size = struct.unpack(">I", data[p + 4:p + 8])[0]
            count = struct.unpack(">I", data[p + 8:p + 12])[0]
            if sample_size:
                info["samples"] = count
                info["samples_bytes"] = sample_size * count
            else:
                info["samples"] = count
                total = 0
                base = p + 12
                for i in range(count):
                    total += struct.unpack(">I", data[base + 4 * i:base + 4 * i + 4])[0]
                info["samples_bytes"] = total

        # 帧间隔
        if info["type"] == "video":
            mdhd = find(data, ts_, te, [b"mdia", b"mdhd"])
            media_ts = None
            if mdhd:
                p = mdhd[0]
                media_ts = struct.unpack(">I", data[p + (20 if data[p] == 1 else 12):
                                                      p + (24 if data[p] == 1 else 16)])[0]
            stts = find(data, ts_, te, [b"mdia", b"minf", b"stbl", b"stts"])
            if stts and media_ts:
                p = stts[0]
                n = struct.unpack(">I", data[p + 4:p + 8])[0]
                deltas, base = [], p + 8
                for i in range(n):
                    cnt, delta = struct.unpack(">II", data[base + 8 * i:base + 8 * i + 8])
                    deltas.append((cnt, delta / media_ts))
                max_delta = max((d for _, d in deltas), default=0)
                info["max_frame_gap_s"] = round(max_delta, 3)
                info["stts_rows"] = n
        tracks.append(info)

    out["tracks"] = tracks
    return out


def human(sec):
    return "{} 分 {:05.2f} 秒".format(int(sec // 60), sec % 60)


def main(path):
    r = parse(path)
    print("=" * 60)
    print("文件：", path.split("\\")[-1])
    print("大小：{:.1f} MB".format(r["file_size"] / 1048576))
    if "error" in r:
        print("错误：", r["error"])
        return 1
    d = r["duration_s"]
    print("时长：{}（{:.2f} 秒）".format(human(d), d))
    print("→ 规程要求 ≤300 秒：", "通过" if d <= 300 else "不通过")
    print()

    ok = True
    v = next((t for t in r["tracks"] if t["type"] == "video"), None)
    a = next((t for t in r["tracks"] if t["type"] == "audio"), None)

    if v:
        w, h = v.get("width"), v.get("height")
        fps = (v.get("samples") or 0) / d if d else 0
        print("视频：{}×{}  {}  {} 帧".format(w, h, v.get("codec"), v.get("samples")))
        print("  实际帧率：{:.1f} fps".format(fps))
        print("  最大帧间隔：{:.2f} 秒".format(v.get("max_frame_gap_s", 0)))
        print("  → 分辨率 ≥1080P：", "通过" if (w or 0) >= 1920 and (h or 0) >= 1080 else "不通过")
        if fps < 24:
            print("  ! 帧率偏低，说明有明显丢帧")
            ok = False
        if v.get("max_frame_gap_s", 0) > 0.4:
            print("  ! 存在超过 0.4 秒的帧间隔，画面会卡顿")
            ok = False
    else:
        print("视频轨：未找到")
        ok = False

    print()
    if a:
        kbps = (a.get("samples_bytes") or 0) * 8 / d / 1000 if d else 0
        print("音频：{}  平均码率 {:.1f} kbps".format(a.get("codec"), kbps))
        if kbps < 8:
            print("  ! 音频码率极低，很可能整轨静音（麦克风没录进去）")
            ok = False
        elif kbps < 24:
            print("  ? 音频码率偏低，建议回放确认人声清楚")
        else:
            print("  → 音频有实际内容")
    else:
        print("音频轨：不存在（无声视频）")
        ok = False

    print()
    print("结论：" + ("技术指标全部通过" if ok else "存在问题，见上面 ! 项"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
