from app.visits.utils.enumerations.visit_enums import VisitStatus


class VisitNotFoundError(Exception):
    def __init__(self) -> None:
        super().__init__("Visit not found")


class InvalidVisitStatusError(Exception):
    def __init__(self, status: VisitStatus) -> None:
        self.status = status
        detail = {
            VisitStatus.SCHEDULED: "Visit not started yet",
            VisitStatus.COMPLETED: "Visit already completed",
            VisitStatus.CANCELED: "Visit already canceled",
            VisitStatus.MISSED: "Visit already missed",
        }.get(status, "Visit must be in progress")
        super().__init__(detail)


class VisitCompletionError(Exception):
    pass
