"""ORM models. Import this package to register all tables on ``Base.metadata``."""

from app.models.ai import AIProposalDecision
from app.models.approvals import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalRule,
    ApproverScope,
    InAppNotification,
    NotificationDelivery,
)
from app.models.audit import AuditEvent
from app.models.base import Base
from app.models.booking import (
    Booking,
    BookingPeriod,
    BookingSchedule,
    BookingSeries,
    BookingSlot,
    Holiday,
    MultiBooking,
    MultiBookingSlot,
    NotificationOutbox,
    PasswordResetToken,
    Permission,
    Role,
    RolePermission,
    RoomAcl,
    RoomAclPermission,
    RoomCustomField,
    RoomCustomFieldOption,
    RoomCustomFieldValue,
    RoomGroup,
    TermBookingSettings,
    TermDate,
    TermSchedule,
    TimetableWeek,
    Translation,
    UserConstraint,
)
from app.models.catalog import Building, Course, Faculty, Instructor, Program, Room, Term, Week
from app.models.channels import (  # noqa: F401
    ChannelDelivery,
    ChannelDepartmentTarget,
    ChannelLinkCode,
    NotifyChannelConfig,
    UserChannel,
)
from app.models.conflicts import BookingConflict  # noqa: F401
from app.models.council import CouncilArtifact, CouncilJob, CouncilStep
from app.models.error_event import ErrorEvent  # noqa: F401  (W3-OPS grouped error events, alembic 0036)
from app.models.integrations import (
    CalendarClassRevision,
    CalendarConnection,
    CalendarEventLink,
    CalendarEventRevision,
    CalendarFeedToken,
    CalendarSyncJob,
    OAuthState,
    WebhookDelivery,
    WebhookEndpoint,
)
from app.models.invigilation import InvigilationDuty, InvigilationPlan, InvigilatorPoolMember
from app.models.kvkk import (  # noqa: F401
    AuditPurgeWindow,
    Consent,
    DsrRequest,
    NoticeAck,
    PrivacyNotice,
    RetentionPolicy,
)
from app.models.learning import LearnedObservation, LearnedPrior, LearningReset, SuggestionFeedback
from app.models.locks import TermLock
from app.models.planning_drafts import PriorityOverride, ProgramDraft
from app.models.policies import BookingPolicy  # noqa: F401
from app.models.runs import Assignment, ChatApplyClaim, ChatMessage, ScheduleRun
from app.models.scheduling import (
    Block,
    ConstraintRow,
    ExamRequest,
    MeetingRequest,
    Section,
    SectionInstructor,
)
from app.models.sso import SsoAuthState, SsoInvite, SsoProvider, SsoRoleMapping, UserIdentity  # noqa: F401
from app.models.studio import ImportedSnapshot, StudioDraft, StudioPreset
from app.models.system import ImportJob, Setting, User

__all__ = [
    "AIProposalDecision",
    "CalendarConnection",
    "CalendarEventLink",
    "CalendarClassRevision",
    "CalendarEventRevision",
    "CalendarFeedToken",
    "CalendarSyncJob",
    "OAuthState",
    "WebhookDelivery",
    "WebhookEndpoint",
    "ApprovalDecision",
    "ApprovalRequest",
    "ApprovalRule",
    "ApproverScope",
    "Assignment",
    "AuditEvent",
    "Base",
    "Block",
    "Booking",
    "BookingPeriod",
    "BookingSchedule",
    "BookingSeries",
    "BookingSlot",
    "Building",
    "ChatApplyClaim",
    "ChatMessage",
    "ConstraintRow",
    "CouncilArtifact",
    "CouncilJob",
    "CouncilStep",
    "Course",
    "ExamRequest",
    "Faculty",
    "Holiday",
    "ImportJob",
    "ImportedSnapshot",
    "InAppNotification",
    "NotificationDelivery",
    "LearnedObservation",
    "LearnedPrior",
    "LearningReset",
    "Instructor",
    "MeetingRequest",
    "MultiBooking",
    "MultiBookingSlot",
    "NotificationOutbox",
    "PasswordResetToken",
    "Permission",
    "InvigilationDuty",
    "InvigilationPlan",
    "InvigilatorPoolMember",
    "Program",
    "ProgramDraft",
    "PriorityOverride",
    "Role",
    "RolePermission",
    "Room",
    "RoomAcl",
    "RoomAclPermission",
    "RoomCustomField",
    "RoomCustomFieldOption",
    "RoomCustomFieldValue",
    "RoomGroup",
    "ScheduleRun",
    "Section",
    "SectionInstructor",
    "Setting",
    "StudioDraft",
    "StudioPreset",
    "SuggestionFeedback",
    "Term",
    "TermBookingSettings",
    "TermDate",
    "TermLock",
    "TermSchedule",
    "TimetableWeek",
    "Translation",
    "User",
    "UserConstraint",
    "Week",
]

# wave 3 W3-AI: AI gateway usage metering (alembic 0034_ai_usage)
from app.models.ai_usage import AIUsage  # noqa: E402

__all__ += ["AIUsage"]

# adaptive scheduling AS-03 / AS-05 / AS-13: season profiles, period segments, demand ledger, learning versions
from app.models.seasons import DemandEvent, SeasonProfile, SeasonSegment  # noqa: E402

__all__ += ["DemandEvent", "SeasonProfile", "SeasonSegment"]

# welcome guide per role WG-01: per-user progress + admin text overrides (alembic 0040_welcome_guide)
from app.models.welcome import WelcomeContent, WelcomeProgress  # noqa: E402

__all__ += ["WelcomeContent", "WelcomeProgress"]
