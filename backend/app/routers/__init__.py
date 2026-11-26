"""业务路由汇总：跨模块链接/告警核查路由必须先于通用资源路由注册。"""
from __future__ import annotations

from app.routers import alert_review, cross_links, resource

ROUTERS = [alert_review, cross_links, resource]
