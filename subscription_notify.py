import os
import requests

NOTION_API_TOKEN = os.getenv("NOTION_SUBSCRIPTION_TOKEN")
NOTION_DB_ID = os.getenv("NOTION_SUBSCRIPTION_DB_ID")
PUSHOVER_TOKEN = os.getenv("PUSHOVER_SUBSCRIPTION_TOKEN")
PUSHOVER_USER = os.getenv("PUSHOVER_USER")

# Notion API 헤더
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# Notion 데이터 가져오기 함수
def fetch_notion_data():
    """
    Notion API를 호출하여 데이터베이스의 데이터를 가져옵니다.
    API 요청 후 JSON 데이터를 반환합니다.
    """
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    response = requests.post(url, headers=NOTION_HEADERS)
    response.raise_for_status()
    data = response.json()
    return data


def extract_notion_fields(notion_data):
    """
    Notion API에서 받은 raw 데이터를 파싱하여 필요한 필드(name, cost, date_remaining, status, next_renewal)를 추출합니다.
    추출된 각 항목은 딕셔너리 형태로 리스트에 담아 반환합니다.
    """
    results = []
    for row in notion_data.get("results", []):
        properties = row.get("properties", {})
        # Name
        name = None
        try:
            name = properties["Name"]["title"][0]["plain_text"]
        except Exception:
            name = None
        # Cost
        cost = None
        try:
            cost = properties["Cost"]["number"]
        except Exception:
            cost = None
        # Format cost with thousand separator and "₩" prefix if not None
        if cost is not None:
            cost = f"₩{int(cost):,}"
        # Date Remaining
        date_remaining = None
        try:
            date_remaining = properties["Date Remaining"]["formula"]["number"]
        except Exception:
            date_remaining = None
        # Status
        status = None
        try:
            status = properties["Status"]["status"]["name"]
        except Exception:
            status = None
        # Next Renewal
        next_renewal = properties.get("Next Renewal", {}).get("formula", {}).get("date", {}).get("start", None)
        results.append({
            "name": name,
            "cost": cost,
            "date_remaining": date_remaining,
            "status": status,
            "next_renewal": next_renewal
        })
    return results


def filter_for_notifications(extracted):
    """
    알림 대상 리스트를 필터링합니다.
    1. 상태가 "Active"인 항목만 선택합니다.
    2. date_remaining이 0, 1, 2, 3, 5, 7 중 하나이거나 음수(연체)인 항목만 선택합니다.
    3. date_remaining 값에 따라 due_today, due_soon, overdue 리스트로 분리하여 반환합니다.
    """
    allowed_days = {1, 2, 3, 5, 7}
    filtered = [
        item for item in extracted
        if item.get("status") == "Active"
        and (item.get("date_remaining") == 0 or item.get("date_remaining") in allowed_days or (item.get("date_remaining") is not None and item.get("date_remaining") < 0))
    ]
    due_today = [item for item in filtered if item.get("date_remaining") == 0]
    due_soon = [item for item in filtered if item.get("date_remaining") in allowed_days]
    overdue = [item for item in filtered if item.get("date_remaining") is not None and item.get("date_remaining") < 0]
    return (due_today, due_soon, overdue)

def generate_notification_messages(overdue, due_today, due_soon):
    """
    알림 메시지를 생성합니다.
    overdue, due_today, due_soon 리스트를 받아 각각의 상태에 맞는 메시지를 생성하여 리스트로 반환합니다.
    """
    messages = []
    if overdue:
        lines = ["❗ 결제 예정일이 지난 서비스가 있습니다!"]
        for item in overdue:
            name = item.get("name") or ""
            cost = item.get("cost") or ""
            date_remaining = item.get("date_remaining")
            next_renewal = item.get("next_renewal") or ""
            # For overdue, display D+{abs(date_remaining)} instead of D--n
            lines.append(f"  • {name} | {cost} | D+{abs(date_remaining)} ({next_renewal})")
        messages.append("\n".join(lines))
    if due_today:
        lines = ["❗ 오늘 결제 예정인 서비스가 있습니다."]
        for item in due_today:
            name = item.get("name") or ""
            cost = item.get("cost") or ""
            next_renewal = item.get("next_renewal") or ""
            lines.append(f"  • {name} | {cost} | D-0 ({next_renewal})")
        messages.append("\n".join(lines))
    if due_soon:
        lines = ["⚠️ 일주일 이내 결제 예정인 서비스가 있습니다."]
        for item in due_soon:
            name = item.get("name") or ""
            cost = item.get("cost") or ""
            date_remaining = item.get("date_remaining")
            next_renewal = item.get("next_renewal") or ""
            # D-{date_remaining} ({next_renewal}), but date_remaining should not be 0 here
            lines.append(f"  • {name} | {cost} | D-{date_remaining} ({next_renewal})")
        messages.append("\n".join(lines))
    return messages

def send_pushover_message(token, user, message):
    """
    Pushover API를 통해 푸시 알림 메시지를 전송합니다.
    token, user, message를 받아 POST 요청을 보냅니다.
    """
    pushover_url = "https://api.pushover.net/1/messages.json"
    payload = {
        "token": token,
        "user": user,
        "message": message
    }
    response = requests.post(pushover_url, data=payload)
    response.raise_for_status()

def lambda_handler(event, context):
    # You can switch between live Notion API data and test data by commenting/uncommenting below:
    notion_data = fetch_notion_data()  # For live API
    # notion_data = TEST_NOTION_DATA      # For testing with mock data
    extracted = extract_notion_fields(notion_data)
    due_today, due_soon, overdue = filter_for_notifications(extracted)
    # Generate and print notification messages
    messages = generate_notification_messages(overdue, due_today, due_soon)
    for message in messages:
        print("\n" + message)
        if PUSHOVER_TOKEN and PUSHOVER_USER:
            send_pushover_message(PUSHOVER_TOKEN, PUSHOVER_USER, message)