from requests_html import HTMLSession
from requests import Response

from urllib3 import disable_warnings, exceptions
import credentials as cred
from magic import from_buffer
from time import sleep
from os import makedirs
from os.path import join, exists
import json


""" 
- get list of links from site
- if one or more files are NOT in list.json
    - add them with is_sent = false
    - run email sender script
"""


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
    "user": cred.username,
    "psw": cred.password,
    "db": "juniorweb",
    "language": "IT",
    "csrfp_token": "UNSET",  #! Will be set by login()
}


def login(
    session: HTMLSession, login_url: str, headers: dict, data: dict
) -> tuple[HTMLSession, Response]:
    # Step 1: Get the login page
    response = session.get(login_url)
    response.html.render()

    # extraxt token from rendered page and add it to payload
    data["csrfp_token"] = session.cookies.get("csrfp_token")

    # Step 5: Submit login request
    response = session.post(login_url, headers=headers, data=data, allow_redirects=True)
    response.html.render

    # Step 6: Validate login
    if cred.username in response.html.text:
        return (session, response)
    return (None, None)


def optional_file_download(response, filename: str):
    if not SKIP_DOWNLOAD:
        makedirs("data", exist_ok=True)
        open(join("data", filename), "wb").write(response.content)


def extract_live_file_list(
    response_to_search_into: Response,
) -> list[dict[str, str, bool, bool]]:
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
                    "is_valid_pdf": None,
                    "is_sent": None,
                }
            )
    return live_file_list


def buffer_is_pdf(buffer) -> tuple[bool, str]:
    detected_type: str = from_buffer(buffer)
    return ("PDF document" in detected_type, detected_type)


def dump_json(data, filepath: str):
    with open(filepath, "w") as f:
        json.dump(data, f)


def list_difference_asymmetric(primary: list, secondary: list) -> list:
    # return elements which are in primary but not in secondary
    # returned list may be shuffled
    return list(set(primary) - set(secondary))


# Validate login
jw_session, response = login(jw_session, LOGIN_PAGE, jw_headers, jw_login_data)
if not jw_session:
    print("ERROR: Login failed.")
    exit(1)


live_file_list = []
local_file_list = []

if exists("file_list.json"):
    with open("file_list.json", "r") as f:
        local_file_list = json.load(f)

else:
    # create new file list if it doesn't exist
    print("creating new list...")

    live_file_list = extract_live_file_list(response)

    # isolate new files, so we can download only those
    new_files = list_difference_asymmetric(live_file_list, local_file_list)
    if not new_files:
        print("Files already up to date.")
        exit(0)

    for file_entry in new_files:
        print(f"Downloading: {file_entry["file_name"]} ...")
        response = jw_session.get(
            file_entry["file_url"], headers=jw_headers, allow_redirects=True
        )

        is_pdf, mime_str = buffer_is_pdf(response.content)

        if is_pdf:
            file_entry["is_valid_pdf"] = True
            optional_file_download(response, file_entry["file_name"])
            sleep(1.5)
        else:
            file_entry["is_valid_pdf"] = False
            print(f"WARN: unknown file type. Expected PDF, got {mime_str} instead.")
            optional_file_download(response, file_entry["file_name"])
            sleep(1.5)

        dump_json(live_file_list, "file_list.json")

print("Done.")
