import copy
import json
import os
import urllib3
import warnings

import requests

from .._log import logger
from .base_downloader import BaseDownloader
from ..douyin.bogus_sign_utils import CommonUtils
from ..url import UrlParser

warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)


class DouyinDownloader(BaseDownloader):
    def __init__(self, real_url):
        super().__init__(real_url)
        self.common_utils = CommonUtils()
        self.headers = {
            'sec-ch-ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
            'Accept': 'application/json, text/plain, */*',
            'sec-ch-ua-mobile': '?0',
            'User-Agent': self.common_utils.user_agent,
            'sec-ch-ua-platform': '"Windows"',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        self.ms_token = self.common_utils.get_ms_token()
        self.ttwid = '1%7CvDWCB8tYdKPbdOlqwNTkDPhizBaV9i91KjYLKJbqurg%7C1723536402%7C314e63000decb79f46b8ff255560b29f4d8c57352dad465b41977db4830b4c7e'
        self.webid = '7307457174287205926'
        self.cookie = os.getenv("DOUYIN_COOKIE", "").strip()
        self.fetch_html_content()
        self.aweme_id = UrlParser.get_video_id(self.real_url)
        self.data = self.fetch_html_data()
        self.is_note = '/note/' in self.real_url

    def get_cookie_header(self, referer_url):
        if self.cookie:
            return self.cookie
        return f"ttwid={self.ttwid}; __ac_referer={referer_url}"

    def fetch_html_data(self):
        referer_url = f"https://www.douyin.com/video/{self.aweme_id}?previous_page=web_code_link"
        play_url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?device_platform=webapp&aid=6383&channel=channel_pc_web&aweme_id={self.aweme_id}&update_version_code=170400&pc_client_type=1&version_code=190500&version_name=19.5.0&cookie_enabled=true&screen_width=1536&screen_height=864&browser_language=zh-CN&browser_platform=Win32&browser_name=Chrome&browser_version=127.0.0.0&browser_online=true&engine_name=Blink&engine_version=127.0.0.0&os_name=Windows&os_version=10&cpu_core_num=8&device_memory=8&platform=PC&downlink=1.25&effective_type=4g&round_trip_time=50&webid={self.webid}&msToken={self.ms_token}"
        new_headers = copy.deepcopy(self.headers)
        new_headers['Referer'] = referer_url
        new_headers['Cookie'] = self.get_cookie_header(referer_url)
        abogus = self.common_utils.get_abogus(play_url, self.common_utils.user_agent)
        url = f"{play_url}&a_bogus={abogus}"
        response = requests.get(url, headers=new_headers, verify=False, timeout=3)
        if response.text:
            return response.json()
        logger.warning(
            "Failed to fetch Douyin video metadata: status=%s, content_length=%s",
            response.status_code,
            len(response.content),
        )
        return None

    def get_real_video_url(self):
        try:
            data_dict = self.data
            if not data_dict:
                return None
            video_data = data_dict.get('aweme_detail', {}).get('video', {})

            bit_rate = video_data.get('bit_rate')
            if bit_rate and len(bit_rate) > 0:
                play_addr_list = bit_rate[0].get('play_addr', {}).get('url_list', [])
                if len(play_addr_list) > 2:
                    return play_addr_list[2]
                elif len(play_addr_list) > 0:
                    return play_addr_list[0]

            play_addr = video_data.get('play_addr', {}).get('url_list', [])
            if play_addr:
                return play_addr[0] if len(play_addr) > 0 else None

            images = data_dict.get('aweme_detail', {}).get('images', [])
            if images and len(images) > 0:
                url_list = images[0].get('url_list', [])
                if url_list:
                    return url_list[0]

            return None
        except (KeyError, json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to parse video URL: {e}")
            return None

    def get_title_content(self):
        try:
            data_dict = self.data
            if not data_dict:
                return None
            return data_dict['aweme_detail']['desc']
        except (KeyError, json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to parse title content: {e}")
            return None

    def get_cover_photo_url(self):
        try:
            data_dict = self.data
            if not data_dict:
                return None
            video_data = data_dict.get('aweme_detail', {}).get('video', {})

            cover = video_data.get('cover_original_scale', {}).get('url_list', [])
            if cover:
                return cover[0]

            cover = video_data.get('cover', {}).get('url_list', [])
            if cover:
                return cover[0]

            images = data_dict.get('aweme_detail', {}).get('images', [])
            if images and len(images) > 0:
                url_list = images[0].get('url_list', [])
                if url_list:
                    return url_list[0]

            return None
        except (KeyError, json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to parse cover URL: {e}")
            return None

    def get_images(self):
        try:
            data_dict = self.data
            if not data_dict:
                return []
            images = data_dict.get('aweme_detail', {}).get('images', [])
            image_urls = []
            for img in images:
                url_list = img.get('url_list', [])
                if url_list:
                    image_urls.append(url_list[0])
            return image_urls
        except (KeyError, json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to parse images: {e}")
            return []


if __name__ == '__main__':
    real_url = 'https://www.douyin.com/video/7396822576074460467'
    dl = DouyinDownloader(real_url)
    print(dl.get_title_content())
    print(dl.get_cover_photo_url())
    print(dl.get_real_video_url())
