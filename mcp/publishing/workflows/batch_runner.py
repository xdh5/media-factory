"""按请求执行共享发布批次；此模块不调用语言模型。"""

import json
import os
from pathlib import Path
import sys
import time

from ..infrastructure import preview_publication, publish_local_outputs
from ..infrastructure.batch_jobs import account_batch_lock, write_batch


def run_batch(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    os.environ["MEDIA_PUBLISHER_INTERACTION_PATH"] = str(path.with_suffix(".interaction.json"))
    request = data["request"]
    reports = path.with_suffix(".jsonl")
    started = time.monotonic()

    def progress(message):
        data["progress"] = message
        write_batch(path, data)

    try:
        with account_batch_lock(request["account_group"], wait=True):
            data.update(status="running", error=None)
            write_batch(path, data)
            for publication in request["publications"]:
                data["current_date"] = publication["publish_date"]
                progress("核验本次账号、准备成片和查询重复项")
                arguments = {"business_line": request["business_line"],
                             "account_group": request["account_group"], "platforms": request["platforms"],
                             **publication}
                try:
                    if publication.get('toutiao_content_types'):
                        from tools.publish_media.toutiao_contents import publish_finance_toutiao_contents
                        result = publish_finance_toutiao_contents(publication['publish_date'], request['account_group'],
                            publication['production_id'], publication['toutiao_content_types'], progress,
                            publication.get('publish_mode', 'immediate'), publication.get('publish_at', 'now'))
                        data['duplicate_count'] += len(result['skipped'])
                        data['scheduled_count'] += sum(row['record']['status'] == 'scheduled' for row in result['published'])
                        if result['failed']:
                            data['error'] = {'message': '部分头条内容发布失败', 'details': result['failed']}
                    else:
                        prepared = preview_publication(**{key: value for key, value in arguments.items()
                            if key not in {"publish_mode", "publish_at", "publish_at_by_platform"}})
                        data["duplicate_count"] += prepared["duplicate_count"]
                        if request["prepare_only"] or not prepared["publishable_count"]:
                            result = {"prepared_count": len(prepared["items"]), "timings_seconds": prepared["timings_seconds"]}
                        else:
                            result = publish_local_outputs(
                                **{**arguments, "publish_mode": publication.get("publish_mode"),
                                   "publish_at": publication.get("publish_at")}, progress=progress)
                            data["scheduled_count"] += sum(row["record"]["status"] == "scheduled" for row in result["published"])
                except Exception as error:
                    details = getattr(error, "details", {})
                    failure = {"publish_date": publication["publish_date"], "type": type(error).__name__,
                               "message": str(error), "details": details}
                    failures = data.setdefault("failed_publications", [])
                    failures.append(failure)
                    data["error"] = {"message": "部分发布失败", "details": failures}
                    data["scheduled_count"] += sum(row["record"]["status"] == "scheduled"
                                                   for row in details.get("published", []))
                    with reports.open("a", encoding="utf-8") as report:
                        report.write(json.dumps(failure, ensure_ascii=False) + "\n")
                    progress(f"{publication['publish_date']}存在失败，继续处理其余日期")
                    continue
                with reports.open("a", encoding="utf-8") as report:
                    report.write(json.dumps({"publish_date": publication["publish_date"], "result": result}, ensure_ascii=False) + "\n")
                if publication["publish_date"] not in data["completed_dates"]:
                    data["completed_dates"].append(publication["publish_date"])
                write_batch(path, data)
            data.update(status='failed' if data.get('error') else ('prepared' if request['prepare_only'] else 'succeeded'), progress=None)
    except Exception as error:
        details = getattr(error, "details", {})
        data.update(status="needs_login" if details.get("login_required") else "failed",
                    error={"type": type(error).__name__, "message": str(error), "details": details})
        partial = details.get("published", [])
        data["scheduled_count"] += sum(row["record"]["status"] == "scheduled" for row in partial)
    finally:
        data["duration_seconds"] = round(time.monotonic() - started, 3)
        write_batch(path, data)


if __name__ == "__main__":
    path = Path(sys.argv[1]).resolve()
    with path.with_suffix(".stdout.log").open("a", encoding="utf-8") as output, path.with_suffix(".log").open("a", encoding="utf-8") as error:
        sys.stdout, sys.stderr = output, error
        run_batch(path)
