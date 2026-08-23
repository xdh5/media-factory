"""为 media-factory 的单个 YouTube 频道生成长期 OAuth 凭据。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow


YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="生成单个 YouTube 频道的 OAuth 凭据")
    parser.add_argument("--client-secret", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--inspect-token", type=Path)
    parser.add_argument("--configure-env", type=Path)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--account", default="language_learning")
    parser.add_argument("--channel-id", default="")
    parser.add_argument("--channel-title", default="")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.configure_env:
        if not args.client_secret or not args.token_file or not args.channel_id:
            parser.error("写入环境配置时必须提供 --client-secret、--token-file 和 --channel-id")
        client_payload = json.loads(args.client_secret.read_text(encoding="utf-8"))
        client = client_payload.get("installed") or client_payload.get("web") or {}
        token = json.loads(args.token_file.read_text(encoding="utf-8"))
        prefix = args.account.strip().upper()
        updates = {
            "YOUTUBE_OAUTH_CLIENT_ID": str(client.get("client_id") or ""),
            "YOUTUBE_OAUTH_CLIENT_SECRET": str(client.get("client_secret") or ""),
            f"{prefix}_YOUTUBE_CHANNEL_ID": args.channel_id.strip(),
            f"{prefix}_YOUTUBE_CHANNEL_TITLE": args.channel_title.strip(),
            f"{prefix}_YOUTUBE_REFRESH_TOKEN": str(token.get("refresh_token") or ""),
        }
        missing = [name for name, value in updates.items() if not value and not name.endswith("_CHANNEL_TITLE")]
        if missing:
            parser.error(f"缺少必要凭据：{', '.join(missing)}")
        lines = args.configure_env.read_text(encoding="utf-8").splitlines() if args.configure_env.is_file() else []
        written = set()
        output = []
        for line in lines:
            key = line.split("=", 1)[0].strip() if "=" in line else ""
            if key in updates:
                output.append(f"{key}={updates[key]}")
                written.add(key)
            else:
                output.append(line)
        if output and output[-1]:
            output.append("")
        for key, value in updates.items():
            if key not in written:
                output.append(f"{key}={value}")
        args.configure_env.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
        print("已写入本地 YouTube 配置：" + "、".join(updates))
        return

    if args.inspect_token:
        credentials = Credentials.from_authorized_user_file(
            str(args.inspect_token),
            scopes=YOUTUBE_SCOPES,
        )
        with build("youtube", "v3", credentials=credentials) as youtube:
            response = youtube.channels().list(part="id,snippet", mine=True).execute()
        channels = [
            {"channel_id": item["id"], "channel_title": item["snippet"]["title"]}
            for item in response.get("items", [])
        ]
        print(json.dumps(channels, ensure_ascii=False))
        return

    if not args.client_secret or not args.output:
        parser.error("生成授权时必须同时提供 --client-secret 和 --output")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(args.client_secret),
        scopes=YOUTUBE_SCOPES,
    )
    credentials = flow.run_local_server(
        host="localhost",
        bind_addr="0.0.0.0",
        port=args.port,
        open_browser=False,
        authorization_prompt_message="请在浏览器打开此地址完成 YouTube 授权：\n{url}\n",
        success_message="YouTube 授权成功，可以关闭此页面。",
    )
    args.output.write_text(credentials.to_json(), encoding="utf-8")
    print(f"授权凭据已保存到：{args.output}")


if __name__ == "__main__":
    main()
