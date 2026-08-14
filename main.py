import logging
import json
import os
from os import makedirs
from os.path import exists, join
from time import sleep
from requests import RequestException, Response, post
from requests_html import HTMLSession
from urllib3 import disable_warnings, exceptions
from dotenv import load_dotenv
from urllib.parse import unquote, urljoin, urlparse
from utils import buffer_is_pdf, diff_dict_lists

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level="INFO",
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Suppress SSL certificate warnings
disable_warnings(exceptions.InsecureRequestWarning)

# Constants
COMPANY_NAME = os.environ.get("COMPANY")
USERNAME = os.environ.get("USERNAME")
PASSWORD = os.environ.get("PASSWORD")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

# Validate environment variables
missing_vars = []
if not COMPANY_NAME:
    missing_vars.append("COMPANY")
if not USERNAME:
    missing_vars.append("USERNAME")
if not PASSWORD:
    missing_vars.append("PASSWORD")
if not NTFY_TOPIC:
    missing_vars.append("NTFY_TOPIC")

if missing_vars:
    logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    logger.error(
        "Please ensure you have set these in your .env file or GitHub Secrets."
    )
    exit(1)

BASE_URL = f"https://juniorweb.{COMPANY_NAME}.it/juniorweb"
LOGIN_PAGE = f"{BASE_URL}/index.php"
SKIP_DOWNLOAD = False
DATA_DIR = "data"
FILE_LIST = "file_list.json"


def send_notification(new_files):
    if not NTFY_TOPIC:
        logger.info("No NTFY_TOPIC set, skipping notification.")
        return []

    if not new_files:
        return []

    logger.info(f"Sending notifications for {len(new_files)} new files...")
    notified_filenames = []

    for file_entry in new_files:
        filename = file_entry["file_name"]
        file_path = join(DATA_DIR, filename)

        if not exists(file_path):
            logger.warning(
                f"File {file_path} not found, sending notification without attachment."
            )
            try:
                post(
                    f"https://ntfy.sh/{NTFY_TOPIC}",
                    data=f"Downloaded {filename} (but file not found locally)".encode(
                        "utf-8"
                    ),
                    headers={
                        "X-Title": "Juniorweb Download Error",
                        "X-Tags": "warning",
                    },
                )
                notified_filenames.append(filename)
            except Exception as e:
                logger.error(f"Failed to send error notification: {e}")
            continue

        logger.info(f"Sending notification for {filename} with attachment...")
        try:
            with open(file_path, "rb") as f:
                file_content = f.read()

                response = post(
                    f"https://ntfy.sh/{NTFY_TOPIC}",
                    data=file_content,
                    headers={
                        "X-Title": "Nuova busta Marco",
                        "X-Message": f"File: {filename}",
                        "X-Filename": filename,
                        "X-Tags": "moneybag",
                    },
                )
            response.raise_for_status()
            logger.info(f"Notification for {filename} sent successfully.")
            notified_filenames.append(filename)
        except Exception as e:
            logger.error(f"Failed to send notification for {filename}: {e}")

        # Avoid rate limiting
        sleep(1)

    return notified_filenames


# Headers for the requests
jw_headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "it-IT,it;q=0.8",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded",
    "Host": f"juniorweb.{COMPANY_NAME}.it",
    "Origin": f"https://juniorweb.{COMPANY_NAME}.it",
    "Referer": f"https://juniorweb.{COMPANY_NAME}.it/juniorweb/index.php",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

jw_login_data = {
    "user": USERNAME,
    "psw": PASSWORD,
    "db": "juniorweb",
    "language": "IT",
    "csrfp_token": "UNSET",  # Will be set by login()
}


def login(
    session: HTMLSession, login_url: str, headers: dict, data: dict
) -> tuple[HTMLSession | None, Response | None]:
    logger.info("Attempting to access the login page.")
    try:
        response = session.get(login_url)
        response.raise_for_status()

        # Extract token from the login page and add it to the payload.
        data["csrfp_token"] = session.cookies.get("csrfp_token")
        logger.info("Extracted CSRF token from the login page.")

        logger.info("Submitting login request.")
        response = session.post(
            login_url, headers=headers, data=data, allow_redirects=True
        )
        response.raise_for_status()
    except RequestException as exc:
        logger.error("Portal login request failed: %s", exc)
        return None, None

    response_text = response.html.text
    response_path = urlparse(response.url).path.casefold()
    response_text_casefolded = response_text.casefold()

    # A valid username is also present on the portal's mandatory password-change
    # page, so it cannot be used as the only login-success check.
    if (
        "cambiapsw.php" in response_path
        or "cambio password obbligatorio" in response_text_casefolded
    ):
        logger.error(
            "The portal requires a mandatory password change (status=%s, path=%s). "
            "Update the portal password before rerunning.",
            response.status_code,
            response_path,
        )
        return None, None

    if USERNAME not in response_text:
        logger.error(
            "Login failed (status=%s, final path=%s).",
            response.status_code,
            response_path,
        )
        return None, None

    logger.info(
        "Login successful (status=%s, final path=%s).",
        response.status_code,
        response_path,
    )
    return session, response


def optional_file_download(response: Response, filename: str):
    if not SKIP_DOWNLOAD:
        logger.info(f"Downloading file: {filename}")
        makedirs(DATA_DIR, exist_ok=True)
        with open(join(DATA_DIR, filename), "wb") as file:
            file.write(response.content)


def _clean_text(value) -> str:
    return " ".join(str(value or "").split())


def _page_title(response: Response) -> str:
    title = response.html.find("title", first=True)
    return _clean_text(title.text) if title else ""


def extract_live_files(response: Response):
    logger.info("Extracting live files from the response.")
    anchors = response.html.find("a")
    live_file_list = []
    seen_urls = set()
    pdf_candidates = 0

    for anchor in anchors:
        href = _clean_text(anchor.attrs.get("href"))
        if not href or href.casefold().startswith(("javascript:", "#")):
            continue

        labels = [
            _clean_text(anchor.text),
            _clean_text(anchor.attrs.get("download")),
            _clean_text(anchor.attrs.get("title")),
            _clean_text(anchor.attrs.get("aria-label")),
            _clean_text(anchor.attrs.get("data-filename")),
        ]
        searchable_text = " ".join(value for value in [*labels, href] if value)
        if ".pdf" not in searchable_text.casefold():
            continue

        pdf_candidates += 1
        file_name = next(
            (label for label in labels if ".pdf" in label.casefold()),
            "",
        )
        if not file_name:
            file_name = _clean_text(unquote(urlparse(href).path.rsplit("/", 1)[-1]))
        if not file_name:
            logger.warning("Skipping PDF link without a filename: %s", href)
            continue

        file_url = urljoin(f"{BASE_URL}/", href)
        if file_url in seen_urls:
            continue
        seen_urls.add(file_url)
        live_file_list.append(
            {
                "file_name": file_name,
                "file_url": file_url,
                "is_sent": False,
            }
        )

    response_path = urlparse(response.url).path if response.url else "<unknown>"
    logger.info(
        "Portal response: status=%s, path=%s, title=%r, anchors=%s, PDF candidates=%s.",
        response.status_code,
        response_path,
        _page_title(response),
        len(anchors),
        pdf_candidates,
    )
    logger.info("Extracted %s live files.", len(live_file_list))
    if not live_file_list:
        logger.error(
            "No PDF files were found in the portal response; refusing to treat it as "
            "an empty payroll list."
        )
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
    if not isinstance(file_list, list) or not file_list:
        raise ValueError("Refusing to overwrite the file list with an empty response.")

    temporary_file = f"{FILE_LIST}.tmp"
    try:
        with open(temporary_file, "w") as f:
            json.dump(file_list, f, indent=2)
            f.write("\n")
        os.replace(temporary_file, FILE_LIST)
    finally:
        if exists(temporary_file):
            os.remove(temporary_file)


if __name__ == "__main__":
    # Initialize a session
    jw_session = HTMLSession()
    jw_session.verify = False

    # Login to the Junior Web portal
    jw_session, response = login(jw_session, LOGIN_PAGE, jw_headers, jw_login_data)
    if not jw_session:
        logger.error("Login failed. Exiting program.")
        exit(1)

    local_file_list = load_local_file_list()
    live_file_list = extract_live_files(response)
    if not live_file_list:
        raise RuntimeError(
            "The portal returned no live files; the existing file list was not changed."
        )

    # Sync is_sent status from local to live
    local_sent_status = {
        f["file_url"]: f.get("is_sent", False) for f in local_file_list
    }
    for f in live_file_list:
        f["is_sent"] = local_sent_status.get(f["file_url"], False)

    # Identify all files that need processing (either new or previously failed notification)
    pending_files = [f for f in live_file_list if not f.get("is_sent")]

    if not pending_files:
        logger.info("Files already up to date. No new files to download.")
    else:
        logger.info(f"Found {len(pending_files)} files to process.")
        for file_entry in pending_files:
            file_path = join(DATA_DIR, file_entry["file_name"])

            # Check if file exists locally, download if missing
            if not exists(file_path):
                logger.info(
                    f"File {file_entry['file_name']} not found locally. Downloading..."
                )
                response = jw_session.get(
                    file_entry["file_url"], headers=jw_headers, allow_redirects=True
                )

                is_pdf, mime_str = buffer_is_pdf(response.content)

                if is_pdf:
                    optional_file_download(response, file_entry["file_name"])
                else:
                    logger.warning(
                        f"Unknown file type. Expected PDF, got {mime_str} instead."
                    )
                    optional_file_download(response, file_entry["file_name"])

                sleep(1.5)
            else:
                logger.info(
                    f"File {file_entry['file_name']} already exists. Skipping download."
                )

    # Identify files that need notification (unsent)
    # Re-evaluate pending_files or just use the same list,
    # but send_notification checks for file existence anyway.
    if pending_files:
        sent_filenames = send_notification(pending_files)
        # Update is_sent in live_file_list
        for f in live_file_list:
            if f["file_name"] in sent_filenames:
                f["is_sent"] = True

    save_file_list(live_file_list)
    logger.info("All tasks completed.")
