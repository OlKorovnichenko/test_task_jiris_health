from enum import StrEnum


class VisitStatus(StrEnum):
    SCHEDULED = "Scheduled"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
    CANCELED = "Canceled"
    MISSED = "Missed"
