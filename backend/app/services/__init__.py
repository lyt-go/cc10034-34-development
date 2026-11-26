"""领域服务注册表：通用资源路由按模块 key 分派到独立业务服务。"""
from __future__ import annotations

from app.services.base import BaseModuleService
from app.services.mask_rule import MaskRuleService
from app.services.privacy_budget import PrivacyBudgetService
from app.services.noise_engine import NoiseEngineService
from app.services.secure_agg import SecureAggService
from app.services.access_audit import AccessAuditService
from app.services.grant_approval import GrantApprovalService
from app.services.classify_tag import ClassifyTagService
from app.services.federated_train import FederatedTrainService
from app.services.gradient_encrypt import GradientEncryptService
from app.services.pseudonym import PseudonymService
from app.services.k_anonymity import KAnonymityService
from app.services.differential_sql import DifferentialSqlService
from app.services.encrypt_index import EncryptIndexService
from app.services.watermark import WatermarkService
from app.services.consent_registry import ConsentRegistryService
from app.services.risk_scan import RiskScanService
from app.services.deploy_policy import DeployPolicyService
from app.services.anomaly_detect import AnomalyDetectService
from app.services.budget_alert import BudgetAlertService
from app.services.budget_txn import BudgetTxnService
from app.services.verification_receipt import VerificationReceiptService
from app.services.correction_request import CorrectionRequestService

SERVICES: dict[str, BaseModuleService] = {
    "mask_rule": MaskRuleService(),
    "privacy_budget": PrivacyBudgetService(),
    "noise_engine": NoiseEngineService(),
    "secure_agg": SecureAggService(),
    "access_audit": AccessAuditService(),
    "grant_approval": GrantApprovalService(),
    "classify_tag": ClassifyTagService(),
    "federated_train": FederatedTrainService(),
    "gradient_encrypt": GradientEncryptService(),
    "pseudonym": PseudonymService(),
    "k_anonymity": KAnonymityService(),
    "differential_sql": DifferentialSqlService(),
    "encrypt_index": EncryptIndexService(),
    "watermark": WatermarkService(),
    "consent_registry": ConsentRegistryService(),
    "risk_scan": RiskScanService(),
    "deploy_policy": DeployPolicyService(),
    "anomaly_detect": AnomalyDetectService(),
    "budget_alert": BudgetAlertService(),
    "budget_txn": BudgetTxnService(),
    "verification_receipt": VerificationReceiptService(),
    "correction_request": CorrectionRequestService(),
}


def service_for(module: str) -> BaseModuleService | None:
    return SERVICES.get(module)
