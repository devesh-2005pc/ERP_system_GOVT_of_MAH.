import enum


class DepartmentCode(str, enum.Enum):
    MANAGER = "MANAGER"                       # apex - sees/edits everything
    SUB_ADMIN = "SUB_ADMIN"                   # administrative - sees/edits everything except a few reserved actions
    STORE = "STORE"
    PLANNING = "PLANNING"
    DISPATCH = "DISPATCH"
    ACCOUNTS = "ACCOUNTS"
    EMPLOYEE = "EMPLOYEE"                     # normal user, no department-wide data access
    # --- New departments added for press workflow enhancement ---
    DIGITAL_PRINTING = "DIGITAL_PRINTING"    # Digital printing department
    TRADITIONAL_PRINTING = "TRADITIONAL_PRINTING"  # Offset/traditional printing department
    PLATE_MAKING = "PLATE_MAKING"            # Pre-press / CTP plate making
    BINDING = "BINDING"                      # Binding and finishing
    STANDARD = "STANDARD"                    # Quality / standard checking before dispatch
    MECHANIC = "MECHANIC"                    # Machine maintenance and breakdown resolution
    BILLING = "BILLING"                      # Billing department (Excel bill generation)


# Roles/departments that are allowed to see and edit ALL departments' data,
# per explicit requirement: "other departments cannot see each other's data,
# only manager and subordinate admin can see/edit everything".
CROSS_DEPARTMENT_ROLES = {DepartmentCode.MANAGER, DepartmentCode.SUB_ADMIN}


class TxnType(str, enum.Enum):
    OPENING = "OPENING"
    PURCHASE_RECEIPT = "PURCHASE_RECEIPT"
    ISSUE = "ISSUE"
    ADJUSTMENT = "ADJUSTMENT"
    DAMAGE = "DAMAGE"
    RETURN = "RETURN"
    TRANSFER_OUT = "TRANSFER_OUT"
    TRANSFER_IN = "TRANSFER_IN"
    ALLOCATED = "ALLOCATED"       # Reserved/allocated for a job (not yet physically issued)


class RequestStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PARTIALLY_FULFILLED = "PARTIALLY_FULFILLED"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


class PurchaseOrderStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ORDERED = "ORDERED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"


class JobStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ON_HOLD = "ON_HOLD"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"             # Paused by Planning (e.g. for urgent order)
    PARTIAL = "PARTIAL"           # Partial quantity produced, remainder pending


class DispatchStatus(str, enum.Enum):
    PENDING = "PENDING"
    READY = "READY"
    DISPATCHED = "DISPATCHED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class ExpenseCategory(str, enum.Enum):
    MATERIAL_PURCHASE = "MATERIAL_PURCHASE"
    MAINTENANCE = "MAINTENANCE"
    UTILITY = "UTILITY"
    SALARY = "SALARY"
    OTHER = "OTHER"


# --- New enums for press workflow ---

class MachineStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"
    UNDER_MAINTENANCE = "UNDER_MAINTENANCE"
    DECOMMISSIONED = "DECOMMISSIONED"


class PrintingMethod(str, enum.Enum):
    DIGITAL = "DIGITAL"
    OFFSET = "OFFSET"
    KOMORI = "KOMORI"
    SCREEN = "SCREEN"
    OTHER = "OTHER"


class PlateStatus(str, enum.Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class FinishingMethod(str, enum.Enum):
    NONE = "NONE"
    STITCHING = "STITCHING"
    STAPLING = "STAPLING"
    WIRE_BINDING = "WIRE_BINDING"
    PERFECT_BINDING = "PERFECT_BINDING"
    SPIRAL_BINDING = "SPIRAL_BINDING"
    OTHER = "OTHER"


class InspectionStatus(str, enum.Enum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    REWORK_REQUIRED = "REWORK_REQUIRED"


class BillingStatus(str, enum.Enum):
    PENDING = "PENDING"
    BILLED = "BILLED"
    PARTIALLY_BILLED = "PARTIALLY_BILLED"
    CANCELLED = "CANCELLED"


class MaintenanceStatus(str, enum.Enum):
    REPORTED = "REPORTED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    DEFERRED = "DEFERRED"
