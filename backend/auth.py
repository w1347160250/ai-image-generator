import os

import msal
from flask import Blueprint, jsonify, redirect, request, session


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _aad_settings():
    return {
        "client_id": os.environ.get("AAD_CLIENT_ID", "").strip(),
        "client_secret": os.environ.get("AAD_CLIENT_SECRET", "").strip(),
        "tenant_id": os.environ.get("AAD_TENANT_ID", "").strip(),
        "redirect_uri": os.environ.get("AAD_REDIRECT_URI", "").strip(),
    }


def _missing_aad_settings(settings):
    names = {
        "client_id": "AAD_CLIENT_ID",
        "client_secret": "AAD_CLIENT_SECRET",
        "tenant_id": "AAD_TENANT_ID",
        "redirect_uri": "AAD_REDIRECT_URI",
    }
    return [names[key] for key, value in settings.items() if not value]


def _build_msal_app(settings):
    authority = f"https://login.microsoftonline.com/{settings['tenant_id']}"
    return msal.ConfidentialClientApplication(
        client_id=settings["client_id"],
        client_credential=settings["client_secret"],
        authority=authority,
    )


@auth_bp.get("/login")
def login():
    settings = _aad_settings()
    missing = _missing_aad_settings(settings)
    if missing:
        return jsonify({"error": f"Microsoft 登录未配置: {', '.join(missing)}"}), 503

    flow = _build_msal_app(settings).initiate_auth_code_flow(
        scopes=[],
        redirect_uri=settings["redirect_uri"],
    )
    if flow.get("error") or not flow.get("auth_uri"):
        logger_message = flow.get("error_description") or flow.get("error") or "未知错误"
        return jsonify({"error": f"无法启动 Microsoft 登录: {logger_message}"}), 502

    session["aad_auth_flow"] = flow
    return redirect(flow["auth_uri"])


@auth_bp.get("/callback")
def callback():
    flow = session.pop("aad_auth_flow", None)
    if not flow:
        return jsonify({"error": "登录会话不存在或已过期，请重新登录"}), 400

    settings = _aad_settings()
    missing = _missing_aad_settings(settings)
    if missing:
        return jsonify({"error": f"Microsoft 登录未配置: {', '.join(missing)}"}), 503

    try:
        result = _build_msal_app(settings).acquire_token_by_auth_code_flow(
            flow,
            request.args.to_dict(flat=True),
        )
    except ValueError:
        return jsonify({"error": "登录回调校验失败，请重新登录"}), 400

    if result.get("error"):
        message = result.get("error_description") or result["error"]
        return jsonify({"error": f"Microsoft 登录失败: {message}"}), 401

    claims = result.get("id_token_claims") or {}
    user_id = claims.get("oid") or claims.get("sub")
    if not user_id:
        return jsonify({"error": "Microsoft 登录响应缺少用户标识"}), 401

    username = claims.get("preferred_username") or claims.get("email") or ""
    session["aad_user"] = {
        "id": user_id,
        "name": claims.get("name") or username or "Microsoft 用户",
        "username": username,
    }
    return redirect("/")


@auth_bp.get("/status")
def status():
    user = session.get("aad_user")
    if not user:
        return jsonify({"authenticated": False, "user": None})
    return jsonify({"authenticated": True, "user": user})


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.pop("aad_user", None)
    session.pop("aad_auth_flow", None)
    return jsonify({"authenticated": False})
