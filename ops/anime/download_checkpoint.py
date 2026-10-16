"""增量分块保存下载进度，后台只上传新块。"""

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.mcp.anime._errors import AnimeError
from core.mcp.anime.services.compile import _probe, _write_json, _validate_audio, assemble_videos
from core.mcp.anime.services.youtube import _file_sha256

CHECKPOINT_NAME = "block-checkpoint.json"


class CheckpointUploader:
    """最多一个后台块加一个当前批次，上传落后时等待，限制未保存数据量。"""

    def __init__(self, directory, prefix, execution_id, sources, exists, fetch, upload, progress,
                 block_seconds=900, block_bytes=128 * 1024 * 1024):
        self.directory = Path(directory)
        self.prefix, self.execution_id, self.sources = prefix, execution_id, sources
        self.upload, self.progress = upload, progress
        self.block_seconds, self.block_bytes = block_seconds, block_bytes
        self.pending = []
        self.pending_seconds, self.pending_bytes = 0.0, 0
        self.future = None
        self.inflight_last = 0
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="anime-checkpoint")
        self.checkpoint = {"version": 2, "execution_id": execution_id,
                           "completed_source_count": 0, "source_ids": [], "blocks": []}
        try:
            if exists(f"{prefix}/{CHECKPOINT_NAME}"):
                path = self.directory / CHECKPOINT_NAME
                fetch(f"{prefix}/{CHECKPOINT_NAME}", path)
                self.checkpoint = json.loads(path.read_text(encoding="utf-8"))
                self._validate_index()
                for block in self.checkpoint["blocks"]:
                    for part in block["parts"]:
                        local = self.directory / part["name"]
                        local.parent.mkdir(parents=True, exist_ok=True)
                        self.progress(f"恢复检查点块：来源 {block['first_source_order']}—{block['last_source_order']}")
                        fetch(f"{prefix}/{part['name']}", local)
                        if _file_sha256(local) != part["sha256"]:
                            raise AnimeError("检查点分块摘要不一致")
                        if abs(_probe(local)["duration"] - float(part["duration_seconds"])) > 1:
                            raise AnimeError("检查点分块实际时长不一致")
                    if block.get("audio_validation") != 1:
                        try:
                            for part in block["parts"]:
                                _validate_audio(self.directory / part["name"])
                        except AnimeError:
                            self.progress(f"检查点音频损坏，仅重建来源 {block['first_source_order']}—{block['last_source_order']}")
                            self._repair_block(block)
                        block["audio_validation"] = 1
                        _write_json(path, self.checkpoint)
                        upload(path, f"{prefix}/{CHECKPOINT_NAME}", content_type="application/json")
        except BaseException:
            self.executor.shutdown(wait=True)
            raise

    @property
    def completed_count(self):
        return self.checkpoint["completed_source_count"]

    def _repair_block(self, block):
        """已损坏音轨无法靠重封装修复；按冻结来源重新下载这一块，其他块继续复用。"""
        from download_video import download
        first, last = block["first_source_order"], block["last_source_order"]
        folder = self.directory / f"checkpoint-repair-{first}-{last}"
        folder.mkdir(parents=True, exist_ok=True)
        records = []
        for order in range(first, last + 1):
            source = self.sources[order - 1]
            path = folder / f"source-{order}.mp4"
            metadata = download(source["work_url"], path)
            if str(metadata.get("video_id")) != str(source["aweme_id"]):
                raise AnimeError("修复检查点时来源 ID 不一致", {"order": order, "expected_id": source["aweme_id"],
                                                         "actual_id": metadata.get("video_id")})
            probe = _probe(path)
            expected = float(source["duration_seconds"])
            if abs(probe["duration"] - expected) > max(5, expected * 0.02):
                raise AnimeError("修复检查点时来源时长不一致")
            records.append({**metadata, "path": path, "probe": probe, "duration": probe["duration"], "order": order})
        manifest = assemble_videos(records, folder / "repaired", progress=self.progress)
        parts = []
        for index, part in enumerate(manifest["parts"], 1):
            path = Path(part["video_path"])
            _validate_audio(path)
            digest = _file_sha256(path)
            name = f"checkpoint-blocks/block-{first}-{last}-{index}-{digest[:16]}.mp4"
            local = self.directory / name
            local.parent.mkdir(exist_ok=True)
            shutil.copy2(path, local)
            self.upload(local, f"{self.prefix}/{name}")
            parts.append({"name": name, "sha256": digest, "duration_seconds": part["duration_seconds"]})
        block["parts"] = parts
        self.progress(f"损坏检查点已按原来源重建：{first}—{last}")

    def _validate_index(self):
        value = self.checkpoint
        count = value.get("completed_source_count")
        if (value.get("version") != 2 or value.get("execution_id") != self.execution_id
                or type(count) is not int or not 1 <= count <= len(self.sources)
                or value.get("source_ids") != [str(item["aweme_id"]) for item in self.sources[:count]]):
            raise AnimeError("分块检查点与执行清单不一致")
        end = 0
        if not isinstance(value.get("blocks"), list) or not value["blocks"]:
            raise AnimeError("分块检查点缺少视频块")
        for block in value["blocks"]:
            first, last = block["first_source_order"], block["last_source_order"]
            if type(first) is not int or type(last) is not int or first != end + 1 or not first <= last <= count:
                raise AnimeError("检查点来源区间不连续")
            parts = block["parts"]
            if not isinstance(parts, list) or not parts:
                raise AnimeError("检查点视频块为空")
            for part in parts:
                name = part["name"]
                if (not isinstance(name, str) or not name.startswith("checkpoint-blocks/")
                        or Path(name).is_absolute() or ".." in Path(name).parts or "\\" in name
                        or not name.endswith(".mp4")):
                    raise AnimeError("检查点视频块路径无效")
            expected = sum(float(item["duration_seconds"]) for item in self.sources[first - 1:last])
            actual = sum(float(part["duration_seconds"]) for part in parts)
            if abs(actual - expected) > max(5, expected * 0.02):
                raise AnimeError("检查点视频块时长与来源区间不符")
            end = last
        if end != count:
            raise AnimeError("检查点已完成数量与来源区间不一致")

    def _harvest(self, wait=False):
        if self.future is not None and (wait or self.future.done()):
            self.checkpoint = self.future.result()
            self.future = None

    def add(self, source, order):
        self._harvest()
        base = self.inflight_last if self.future is not None else self.completed_count
        if order != base + len(self.pending) + 1:
            raise AnimeError("新增来源未按连续顺序进入检查点")
        self.pending.append(source)
        self.pending_seconds += float(source["duration"])
        self.pending_bytes += Path(source["path"]).stat().st_size
        if self.pending_seconds >= self.block_seconds or self.pending_bytes >= self.block_bytes:
            self._submit_pending()

    def _submit_pending(self):
        self._harvest(wait=True)
        if not self.pending:
            return
        batch = self.pending
        first = self.completed_count + 1
        last = first + len(batch) - 1
        self.pending = []
        self.pending_seconds, self.pending_bytes = 0.0, 0
        self.inflight_last = last
        self.future = self.executor.submit(self._commit_block, batch, first, last, self.checkpoint)

    def _commit_block(self, batch, first, last, previous):
        self.progress(f"后台保存新增检查点块：来源 {first}—{last}")
        folder = self.directory / f"checkpoint-work-{first}-{last}"
        folder.mkdir(parents=True, exist_ok=True)
        if len(batch) == 1:
            path = folder / "part-1.mp4"
            shutil.copy2(batch[0]["path"], path)
            parts = [{"video_path": str(path), "duration_seconds": _probe(path)["duration"]}]
        else:
            parts = assemble_videos(batch, folder, progress=self.progress)["parts"]
        saved = []
        for index, part in enumerate(parts, 1):
            path = Path(part["video_path"])
            _validate_audio(path)
            digest = _file_sha256(path)
            name = f"checkpoint-blocks/block-{first}-{last}-{index}-{digest[:16]}.mp4"
            local = self.directory / name
            local.parent.mkdir(exist_ok=True)
            shutil.move(str(path), str(local))
            self.upload(local, f"{self.prefix}/{name}")
            saved.append({"name": name, "sha256": digest, "duration_seconds": part["duration_seconds"]})
        value = {"version": 2, "execution_id": self.execution_id, "completed_source_count": last,
                 "next_source_order": last + 1,
                 "source_ids": [str(item["aweme_id"]) for item in self.sources[:last]],
                 "blocks": previous["blocks"] + [{"first_source_order": first,
                                                   "last_source_order": last, "parts": saved,
                                                   "audio_validation": 1}]}
        # 最后提交索引；硬终止最多留下未引用的块，不会指向未上传的视频。
        path = self.directory / CHECKPOINT_NAME
        _write_json(path, value)
        self.upload(path, f"{self.prefix}/{CHECKPOINT_NAME}", content_type="application/json")
        # 仅释放本次 Runner 已提交的原片，降低长剧磁盘占用。
        for source in batch:
            original = Path(source["path"]).resolve()
            if original.parent == self.directory.resolve() and original.name.startswith("source-"):
                try:
                    original.unlink(missing_ok=True)
                except OSError:
                    self.progress(f"本地原片释放失败，检查点仍有效：{original.name}")
        self.progress(f"检查点块已提交：来源 {first}—{last}，下次从 {last + 1} 开始")
        return value

    def finish(self):
        """等待后台块并保存尾批次，不重传旧块。"""
        self._submit_pending()
        self._harvest(wait=True)
        return self.completed_count

    def final_sources(self):
        self.finish()
        records = []
        for block in self.checkpoint["blocks"]:
            for part in block["parts"]:
                path = self.directory / part["name"]
                probe = _probe(path)
                records.append({"path": path, "probe": probe, "duration": probe["duration"],
                                "order": len(records) + 1, "title": "已验证来源分块", "topics": []})
        return records

    def close(self):
        self.executor.shutdown(wait=True)
