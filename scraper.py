from concurrent.futures import ThreadPoolExecutor
import time
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from utils import ConfigError, clean_text, requested_term_matches, resolve_search_subject


SEARCH_PAGE_URL = "https://globalsearch.cuny.edu/CFGlobalSearchTool/search.jsp"
CONTROLLER_URL = "https://globalsearch.cuny.edu/CFGlobalSearchTool/CFSearchToolController"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)
CAREERS = {
    "UGRD": "Undergraduate",
    "GRAD": "Graduate",
    "DOCT": "Doctoral",
}


def scrape_sections(
    runtime_config: dict[str, Any],
) -> tuple[requests.Session, list[dict[str, Any]], list[str], list[str], str]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    warnings: list[str] = []

    search_page = request_with_retries(session, "GET", SEARCH_PAGE_URL)
    term_code, term_label = detect_term(search_page.text, runtime_config["term"])
    if term_code is None:
        raise RuntimeError(
            f"{runtime_config['term']} schedule not yet published on CUNY Global Search"
        )

    criteria_page = open_search_criteria(
        session=session,
        institution_code=runtime_config["institution_code"],
        institution_name=runtime_config["institution_name"],
        term_code=term_code,
        term_label=term_label,
    )
    subject_options = parse_subject_options(criteria_page.text)
    if not subject_options:
        raise RuntimeError("Unable to parse subject options from the live CUNY criteria page.")

    all_sections: list[dict[str, Any]] = []
    subject_messages: list[str] = []

    for index, requested_subject in enumerate(runtime_config["course_codes"]):
        if index:
            time.sleep(1)

        try:
            search_subject, subject_display = resolve_search_subject(
                requested_subject, subject_options
            )
        except ConfigError as exc:
            subject_messages.append(str(exc))
            continue

        subject_sections = scrape_subject_across_careers(
            session=session,
            institution_code=runtime_config["institution_code"],
            institution_name=runtime_config["institution_name"],
            term_code=term_code,
            term_label=term_label,
            requested_subject=requested_subject,
            search_subject=search_subject,
            subject_display=subject_display,
            warnings=warnings,
        )

        if subject_sections:
            all_sections.extend(subject_sections)
        else:
            subject_messages.append(
                f"No sections found for {requested_subject} in {runtime_config['term']}"
            )

    return session, all_sections, subject_messages, warnings, term_label


def request_with_retries(
    session: requests.Session,
    method: str,
    url: str,
    *,
    data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int = 30,
) -> requests.Response:
    last_error: Exception | None = None

    for attempt in range(3):
        try:
            response = session.request(
                method=method,
                url=url,
                data=data,
                params=params,
                timeout=timeout,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2)

    raise RuntimeError(f"Request failed after 3 attempts: {url} ({last_error})")


def detect_term(search_page_html: str, requested_term: str) -> tuple[str | None, str]:
    soup = BeautifulSoup(search_page_html, "lxml")
    for option in soup.select("select[name='term_value'] option"):
        value = (option.get("value") or "").strip()
        text = clean_text(option.get_text(" ", strip=True))
        if value and requested_term_matches(text, requested_term):
            return value, text
    return None, requested_term


def open_search_criteria(
    session: requests.Session,
    institution_code: str,
    institution_name: str,
    term_code: str,
    term_label: str,
) -> requests.Response:
    payload = {
        "selectedInstName": f"{institution_name} |",
        "inst_selection": institution_code,
        "selectedTermName": term_label,
        "term_value": term_code,
        "next_btn": "Next",
    }
    return request_with_retries(session, "POST", CONTROLLER_URL, data=payload)


def parse_subject_options(criteria_html: str) -> dict[str, str]:
    soup = BeautifulSoup(criteria_html, "lxml")
    options: dict[str, str] = {}
    for option in soup.select("select[name='subject_name'] option"):
        code = (option.get("value") or "").strip().upper()
        name = clean_text(option.get_text(" ", strip=True))
        if code:
            options[code] = name
    return options


def scrape_subject_across_careers(
    session: requests.Session,
    institution_code: str,
    institution_name: str,
    term_code: str,
    term_label: str,
    requested_subject: str,
    search_subject: str,
    subject_display: str,
    warnings: list[str],
) -> list[dict[str, Any]]:
    deduped_sections: dict[str, dict[str, Any]] = {}

    for career_code, career_label in CAREERS.items():
        html = submit_subject_search(
            session=session,
            institution_code=institution_code,
            institution_name=institution_name,
            term_code=term_code,
            term_label=term_label,
            subject_code=search_subject,
            subject_label=subject_display,
            career_code=career_code,
            career_label=career_label,
        )
        for section in parse_search_results(
            html=html,
            requested_subject=requested_subject,
            search_subject=search_subject,
            warnings=warnings,
            career_code=career_code,
        ):
            deduped_sections[section["class_number"]] = section

    return list(deduped_sections.values())


def submit_subject_search(
    session: requests.Session,
    institution_code: str,
    institution_name: str,
    term_code: str,
    term_label: str,
    subject_code: str,
    subject_label: str,
    career_code: str,
    career_label: str,
) -> str:
    payload = {
        "selectedInstName": f"{institution_name} |",
        "inst_selection": institution_code,
        "selectedTermName": term_label,
        "term_value": term_code,
        "subject_name": subject_code,
        "selectedSubjectName": subject_label,
        "courseCareer": career_code,
        "selectedCCareerName": career_label,
        "courseAttr": "",
        "selectedCAttrName": "",
        "courseAttrValue": "",
        "selectedCAttrVName": "",
        "reqDesignation": "",
        "selectedReqDName": "",
        "sessionId": "",
        "selectedSessionId": "",
        "selectedModeInsName": "",
        "meetingStart": "LT",
        "selectedMeetingStartName": "less than",
        "meetingStartText": "",
        "AndMeetingStartText": "",
        "meetingEnd": "LE",
        "selectedMeetingEndName": "less than or equal to",
        "meetingEndText": "",
        "AndMeetingEndText": "",
        "daysOfWeek": "I",
        "selectedDaysOfWeekName": "include only these days",
        "instructor": "B",
        "selectedInstructorName": "begins with",
        "instructorName": "",
        "search_btn_search": "Search",
    }

    response = request_with_retries(session, "POST", CONTROLLER_URL, data=payload)
    return response.text


def parse_search_results(
    html: str,
    requested_subject: str,
    search_subject: str,
    warnings: list[str],
    career_code: str,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    if "Criteria" in title:
        return []
    if "Results" not in title:
        log_warning(
            warnings,
            f"Unexpected HTML structure while parsing {requested_subject} ({career_code}); results page title was '{title or 'missing'}'.",
        )
        return []

    sections: list[dict[str, Any]] = []
    for table in soup.select("table.classinfo"):
        header_div = table.find_previous("div", class_="testing_msg")
        if not header_div:
            log_warning(
                warnings,
                f"Skipped a table for {requested_subject} because the course header block was missing.",
            )
            continue

        course_header = clean_text(header_div.get_text(" ", strip=True))
        course_display, course_title = split_course_header(course_header)
        if not course_display:
            log_warning(
                warnings,
                f"Skipped a table for {requested_subject} because the course header could not be parsed: '{course_header}'.",
            )
            continue

        for row in table.select("tbody tr"):
            cells = row.find_all("td")
            if len(cells) < 8:
                log_warning(
                    warnings,
                    f"Skipped a malformed section row for {course_display}; expected at least 8 cells and found {len(cells)}.",
                )
                continue

            class_link = cells[0].find("a")
            section_link = cells[1].find("a")
            status_image = cells[7].find("img")

            class_number = clean_text(cells[0].get_text(" ", strip=True))
            detail_href = ""
            if class_link and class_link.get("href"):
                detail_href = urljoin(CONTROLLER_URL, class_link["href"])
            elif section_link and section_link.get("href"):
                detail_href = urljoin(CONTROLLER_URL, section_link["href"])

            sections.append(
                {
                    "requested_subject": requested_subject,
                    "search_subject": search_subject,
                    "career_search_code": career_code,
                    "course": course_display,
                    "course_title": course_title,
                    "section": clean_text(cells[1].get_text(" ", strip=True)),
                    "class_number": class_number,
                    "days_time": clean_text(cells[2].get_text(" ", strip=True)),
                    "room": clean_text(cells[3].get_text(" ", strip=True)),
                    "instructor": clean_text(cells[4].get_text(" ", strip=True)) or "TBA",
                    "modality_raw": clean_text(cells[5].get_text(" ", strip=True)),
                    "meeting_dates": clean_text(cells[6].get_text(" ", strip=True)),
                    "status": status_image.get("alt", "").strip()
                    if status_image
                    else clean_text(cells[7].get_text(" ", strip=True)),
                    "course_topic": clean_text(cells[8].get_text(" ", strip=True))
                    if len(cells) > 8
                    else course_title,
                    "detail_url": detail_href,
                }
            )

    return sections


def split_course_header(header_text: str) -> tuple[str, str]:
    parts = [part.strip() for part in header_text.split(" - ", 1)]
    if len(parts) != 2:
        return "", ""
    return parts[0], parts[1]


def log_warning(warnings: list[str], message: str) -> None:
    if message not in warnings:
        warnings.append(message)


def enrich_sections_with_details(session: requests.Session, sections: list[dict[str, Any]]) -> None:
    if not sections:
        return

    with ThreadPoolExecutor(max_workers=4) as executor:
        for section, detail in zip(sections, executor.map(lambda item: fetch_detail(session, item), sections)):
            section.update(detail)


def fetch_detail(
    base_session: requests.Session, section: dict[str, Any]
) -> dict[str, Any]:
    detail_url = section.get("detail_url")
    if not detail_url:
        return {
            "credits": None,
            "meeting_patterns": [],
        }

    try:
        response = request_with_retries(clone_session(base_session), "GET", detail_url)
        return parse_detail_page(response.text)
    except RuntimeError:
        warnings = list(section.get("warnings", []))
        warnings.append("Unable to fetch class details.")
        return {
            "credits": None,
            "meeting_patterns": [],
            "warnings": warnings,
        }


def clone_session(base_session: requests.Session) -> requests.Session:
    session = requests.Session()
    session.headers.update(base_session.headers)
    session.cookies.update(base_session.cookies)
    return session


def parse_detail_page(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")

    units_text = extract_labeled_value(soup, "Units")
    meeting_patterns = parse_meeting_patterns(soup)

    return {
        "credits": parse_credits(units_text),
        "units_text": units_text,
        "class_component": extract_labeled_value(soup, "Class Components"),
        "session": extract_labeled_value(soup, "Session"),
        "career": extract_labeled_value(soup, "Career"),
        "detail_status": extract_labeled_value(soup, "Status"),
        "meeting_patterns": meeting_patterns,
    }


def extract_labeled_value(soup: BeautifulSoup, label: str) -> str:
    for td in soup.find_all("td"):
        text = clean_text(td.get_text(" ", strip=True))
        if text == label:
            next_td = td.find_next("td")
            if next_td:
                return clean_text(next_td.get_text(" ", strip=True))
    return ""


def parse_credits(units_text: str) -> float | None:
    if not units_text:
        return None
    token = units_text.split(" ", 1)[0]
    try:
        return float(token)
    except ValueError:
        return None


def parse_meeting_patterns(soup: BeautifulSoup) -> list[dict[str, Any]]:
    heading = soup.find("b", string=lambda value: value and "Meeting Information" in value)
    if not heading:
        return []

    table = heading.find_next("table", class_="classinfo")
    if not table:
        return []

    patterns: list[dict[str, Any]] = []
    for row in table.select("tbody tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        patterns.append(
            {
                "days_time": clean_text(cells[0].get_text(" ", strip=True)),
                "room": clean_text(cells[1].get_text(" ", strip=True)) or "TBA",
                "instructor": clean_text(cells[2].get_text(" ", strip=True)) or "TBA",
                "meeting_dates": clean_text(cells[3].get_text(" ", strip=True)),
            }
        )
    return patterns
