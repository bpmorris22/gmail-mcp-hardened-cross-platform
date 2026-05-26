from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


class CalendarService:
    def __init__(self, credentials: Credentials, account_name: str = ""):
        self.service = build("calendar", "v3", credentials=credentials)
        self.account_name = account_name

    # ------------------------------------------------------------------ calendars

    def list_calendars(self) -> List[Dict[str, Any]]:
        result = self.service.calendarList().list().execute()
        return [
            {
                "id": cal["id"],
                "summary": cal.get("summary", ""),
                "description": cal.get("description", ""),
                "primary": cal.get("primary", False),
                "accessRole": cal.get("accessRole", ""),
                "backgroundColor": cal.get("backgroundColor", ""),
            }
            for cal in result.get("items", [])
        ]

    # ------------------------------------------------------------------ events

    def list_events(
        self,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        max_results: int = 20,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        params: Dict[str, Any] = {
            "calendarId": calendar_id,
            "maxResults": min(max_results, 50),
            "singleEvents": True,
            "orderBy": "startTime",
            "timeMin": time_min or now,
        }
        if time_max:
            params["timeMax"] = time_max

        result = self.service.events().list(**params).execute()
        events = [self._parse_event(e) for e in result.get("items", [])]
        return {
            "calendar_id": calendar_id,
            "count": len(events),
            "events": events,
            "nextPageToken": result.get("nextPageToken"),
        }

    def search_events(
        self,
        query: str,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        max_results: int = 20,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        params: Dict[str, Any] = {
            "calendarId": calendar_id,
            "q": query,
            "maxResults": min(max_results, 50),
            "singleEvents": True,
            "orderBy": "startTime",
            "timeMin": time_min or now,
        }
        if time_max:
            params["timeMax"] = time_max

        result = self.service.events().list(**params).execute()
        events = [self._parse_event(e) for e in result.get("items", [])]
        return {
            "query": query,
            "count": len(events),
            "events": events,
        }

    def get_event(self, event_id: str, calendar_id: str = "primary") -> Dict[str, Any]:
        event = self.service.events().get(
            calendarId=calendar_id, eventId=event_id
        ).execute()
        return self._parse_event(event)

    # ------------------------------------------------------------------ internals

    def _parse_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        start = event.get("start", {})
        end = event.get("end", {})

        attendees = [
            {
                "email": a.get("email", ""),
                "name": a.get("displayName", ""),
                "response": a.get("responseStatus", ""),
                "self": a.get("self", False),
            }
            for a in event.get("attendees", [])
        ]

        return {
            "id": event.get("id", ""),
            "summary": event.get("summary", "(sin título)"),
            "description": event.get("description", ""),
            "location": event.get("location", ""),
            "start": start.get("dateTime", start.get("date", "")),
            "end": end.get("dateTime", end.get("date", "")),
            "allDay": "date" in start and "dateTime" not in start,
            "status": event.get("status", ""),
            "organizer": event.get("organizer", {}).get("email", ""),
            "attendees": attendees,
            "attendeeCount": len(attendees),
            "meetLink": event.get("hangoutLink", ""),
            "htmlLink": event.get("htmlLink", ""),
            "recurrence": bool(event.get("recurrence") or event.get("recurringEventId")),
        }
