##### downloader_helpers/cleanup.py - 임시 파일 정리 
"""다운로드 중단 시 .part/.ytdl/.f*** 임시 파일 일괄 삭제."""
import glob
import os
import re


def safe_cleanup_temp_files(filepath):
    """작업 중단 시 .part, .ytdl, .f*** 스트림 조각 및 임시 썸네일 일괄 삭제."""
    if not filepath:
        return
    try:
        dir_name = os.path.dirname(filepath)
        file_name = os.path.basename(filepath)

        # f코드 검출 및 제거 (예: .f251, .f137, .f401)
        file_name_clean = re.sub(r"\.f\d+.*$", "", file_name)

        # 일반 확장자 제거 (예: .part, .ytdl, .webm, .mp4)
        file_name_clean = re.sub(
            r"\.(part|ytdl|temp|mp4|webm|mkv|3gp|flv|ts)$", "", file_name_clean, flags=re.IGNORECASE
        )

        base_path = os.path.join(dir_name, file_name_clean)
        search_pattern = base_path + "*"

        for target in glob.glob(search_pattern):
            if target.endswith(
                (
                    ".part",
                    ".ytdl",
                    ".temp",
                    "_temp.ts",
                    "_temp_thumb.jpg",
                    ".webp",
                    ".jpg",
                    ".png",
                )
            ):
                if os.path.exists(target):
                    try:
                        os.remove(target)
                    except Exception:
                        pass
    except Exception:
        pass
