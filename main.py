import logging
from requests_html import HTMLSession
from requests import Response
from urllib3 import disable_warnings, exceptions
import credentials as cred
from time import sleep
from os import makedirs
from os.path import join, exists
from utils import buffer_is_pdf, difference_between_dict_lists
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Suppress SSL certificate warnings
disable_warnings(exceptions.InsecureRequestWarning)

# Initialize a session
jw_session = HTMLSession()
jw_session.verify = False

BASE_URL = "https://juniorweb.mastertech.it/juniorweb"
LOGIN_PAGE = f"{BASE_URL}/index.php"
SKIP_DOWNLOAD = True

# Step 3: Prepare headers
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
    "csrfp_token": "UNSET",  #! Will be set by login()
}


def login(
    session: HTMLSession, login_url: str, headers: dict, data: dict
) -> tuple[HTMLSession, Response]:
    # Step 1: Get the login page
    logger.info("Attempting to access the login page.")
    response = session.get(login_url)
    response.html.render()

    # Extract token from rendered page and add it to payload
    data["csrfp_token"] = session.cookies.get("csrfp_token")

    # Step 5: Submit login request
    logger.info("Submitting login request.")
    response = session.post(login_url, headers=headers, data=data, allow_redirects=True)

    # Step 6: Validate login
    if cred.USERNAME in response.html.text:
        logger.info("Login successful.")
        return (session, response)
    else:
        logger.error("Login failed.")
        return (None, None)


def optional_file_download(response, filename: str):
    if not SKIP_DOWNLOAD:
        logger.info(f"Downloading file: {filename}")
        makedirs("data", exist_ok=True)
        open(join("data", filename), "wb").write(response.content)


def extract_live_files(response_to_search_into: Response):
    logger.info("Extracting live files from the response.")
    anchors = response_to_search_into.html.find("a")
    live_file_list = []
    for a in anchors:
        if ".pdf" in a.text:
            file_name = a.text
            href = a.xpath("//a[@href]/@href")[0]
            file_url = f"{BASE_URL}/{href}"
            live_file_list.append(
                {
                    "file_name": file_name,
                    "file_url": file_url,
                    "is_sent": False,
                }
            )
    logger.info(f"Extracted {len(live_file_list)} live files.")
    return live_file_list


# Validate login
jw_session, response = login(jw_session, LOGIN_PAGE, jw_headers, jw_login_data)
if not jw_session:
    logger.error("Login failed. Exiting program.")
    exit(1)

live_file_list = None
local_file_list = None

if exists("file_list.json"):
    logger.info("Loading existing file list.")
    with open("file_list.json", "r") as f:
        local_file_list = json.load(f)
else:
    logger.info("No existing file list found. Creating a new one.")

live_file_list = extract_live_files(response)

# Isolate new files, so we can download only those
new_files = difference_between_dict_lists(
    live_file_list, local_file_list, keys=["file_name", "file_url"]
)

if not new_files:
    logger.info("Files already up to date. No new files to download.")
    exit(0)

for file_entry in new_files:
    logger.info(f"Downloading: {file_entry['file_name']} ...")
    response = jw_session.get(
        file_entry["file_url"], headers=jw_headers, allow_redirects=True
    )

    is_pdf, mime_str = buffer_is_pdf(response.content)

    if is_pdf:
        optional_file_download(response, file_entry["file_name"])
        sleep(1.5)
    else:
        logger.warning(f"Unknown file type. Expected PDF, got {mime_str} instead.")
        optional_file_download(response, file_entry["file_name"])
        sleep(1.5)

    with open("file_list.json", "w") as f:
        json.dump(live_file_list, f)

logger.info("All tasks completed. Exiting program.")
