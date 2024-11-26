import logging
import json
from os import makedirs
from os.path import exists, join
from time import sleep
from requests import Response
from requests_html import HTMLSession
from urllib3 import disable_warnings, exceptions
import credentials as cred
from utils import buffer_is_pdf, diff_dict_lists

# Configure logging
logging.basicConfig(
    level="INFO",
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Suppress SSL certificate warnings
disable_warnings(exceptions.InsecureRequestWarning)

# Constants
BASE_URL = "https://juniorweb.mastertech.it/juniorweb"
LOGIN_PAGE = f"{BASE_URL}/index.php"
SKIP_DOWNLOAD = False
DATA_DIR = "data"
FILE_LIST = "file_list.json"


# Headers for the requests
jw_headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "it-IT,it;q=0.8",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded",
    "Host": "juniorweb.mastertech.it",
    "Origin": "https://juniorweb.mastertech.it",
    "Referer": "https://juniorweb.mastertech.it/juniorweb/index.php",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

jw_login_data = {
    "user": cred.USERNAME,
    "psw": cred.PASSWORD,
    "db": "juniorweb",
    "language": "IT",
    "csrfp_token": "UNSET",  # Will be set by login()
}


def login(
    session: HTMLSession, login_url: str, headers: dict, data: dict
) -> tuple[HTMLSession, Response]:
    logger.info("Attempting to access the login page.")
    response = session.get(login_url)
    response.html.render()

    # Extract token from rendered page and add it to payload
    data["csrfp_token"] = session.cookies.get("csrfp_token")
    logger.info(f"Extracted csrfp_token: {data['csrfp_token']}")

    logger.info("Submitting login request.")
    response = session.post(login_url, headers=headers, data=data, allow_redirects=True)

    if cred.USERNAME in response.html.text:
        logger.info("Login successful.")
        return session, response
    else:
        logger.error("Login failed.")
        return None, None


def optional_file_download(response: Response, filename: str):
    if not SKIP_DOWNLOAD:
        logger.info(f"Downloading file: {filename}")
        makedirs(DATA_DIR, exist_ok=True)
        with open(join(DATA_DIR, filename), "wb") as file:
            file.write(response.content)


def extract_live_files(response: Response):
    logger.info("Extracting live files from the response.")
    anchors = response.html.find("a")
    live_file_list = [
        {
            "file_name": a.text,
            "file_url": f"{BASE_URL}/{a.xpath('//a[@href]/@href')[0]}",
            "is_sent": False,
        }
        for a in anchors
        if ".pdf" in a.text
    ]
    logger.info(f"Extracted {len(live_file_list)} live files.")
    return live_file_list


def load_local_file_list():
    if exists(FILE_LIST):
        logger.info("Loading existing file list.")
        with open(FILE_LIST, "r") as f:
            return json.load(f)
    else:
        logger.info("No existing file list found. Creating a new one.")
        return []


def save_file_list(file_list):
    with open(FILE_LIST, "w") as f:
        json.dump(file_list, f)


# Initialize a session
jw_session = HTMLSession()
jw_session.verify = False

# Main script
jw_session, response = login(jw_session, LOGIN_PAGE, jw_headers, jw_login_data)
if not jw_session:
    logger.error("Login failed. Exiting program.")
    exit(1)

local_file_list = load_local_file_list()
live_file_list = extract_live_files(response)

# Isolate new files, so we can download only those
new_files = diff_dict_lists(
    live_file_list, local_file_list, keys=["file_name", "file_url"]
)

if not new_files:
    logger.info("Files already up to date. No new files to download.")
    exit(0)

for file_entry in new_files:
    response = jw_session.get(
        file_entry["file_url"], headers=jw_headers, allow_redirects=True
    )

    is_pdf, mime_str = buffer_is_pdf(response.content)

    if is_pdf:
        optional_file_download(response, file_entry["file_name"])
    else:
        logger.warning(f"Unknown file type. Expected PDF, got {mime_str} instead.")
        optional_file_download(response, file_entry["file_name"])

    sleep(1.5)

save_file_list(live_file_list)
logger.info("All tasks completed. Exiting program.")
