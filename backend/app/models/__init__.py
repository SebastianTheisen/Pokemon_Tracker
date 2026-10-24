"""ORM-Modelle. Der Import hier sorgt dafür, dass Alembic alle Tabellen kennt."""

from app.models.alerts import AlertDirection, PriceAlert, PushSubscription
from app.models.audit import AuditLog
from app.models.auth import InviteCode, PasswordResetToken, RefreshToken
from app.models.cardmarket import CmExpansion, CmImport, CmPrice, CmProduct, ExpansionLinkSource
from app.models.catalog import Card, CardSet, CardSource, ImageSource
from app.models.collection import (
    CollectionEvent,
    CollectionEventType,
    CollectionItem,
    Folder,
    FolderSnapshot,
    GradingCompany,
    PortfolioSnapshot,
    Product,
    ProductKind,
    WishlistItem,
)
from app.models.images import ImageImportRun, ImageProbe, OfficialCard
from app.models.pricing import (
    CardPriceLink,
    EbayFetch,
    PriceChartingDetail,
    PriceCheck,
    PricePoint,
    PsaCertRecord,
)
from app.models.reports import MissingReport, ReportKind
from app.models.scanner import CardReferenceImage, ScanLog, ScanMode
from app.models.settings import UserSettings
from app.models.trades import Trade
from app.models.user import Role, User

__all__ = [
    "AlertDirection",
    "AuditLog",
    "Card",
    "CardPriceLink",
    "CardReferenceImage",
    "CardSet",
    "CardSource",
    "CmExpansion",
    "CmImport",
    "CmPrice",
    "CmProduct",
    "CollectionEvent",
    "CollectionEventType",
    "CollectionItem",
    "EbayFetch",
    "ExpansionLinkSource",
    "Folder",
    "FolderSnapshot",
    "GradingCompany",
    "ImageImportRun",
    "ImageProbe",
    "ImageSource",
    "InviteCode",
    "MissingReport",
    "OfficialCard",
    "PasswordResetToken",
    "PortfolioSnapshot",
    "PriceAlert",
    "PriceChartingDetail",
    "PriceCheck",
    "PricePoint",
    "Product",
    "ProductKind",
    "PsaCertRecord",
    "PushSubscription",
    "RefreshToken",
    "ReportKind",
    "Role",
    "ScanLog",
    "ScanMode",
    "Trade",
    "User",
    "UserSettings",
    "WishlistItem",
]
