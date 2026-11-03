"""Personal-vs-work attestation is made in the user's local browser, never Codex."""

from __future__ import annotations

from typing import Any

from .gmail import GmailTransport, PrivateConfig
from .reports import OperationalMetrics
from .runner import PersonalApprovals, discovery, quiet_private_runtime
from .security import PrivateError, require_external_terminal, secure_directory
from .web import LocalReviewServer, browser_script, json_response, serve


def review_server(config: PrivateConfig, transport: GmailTransport) -> LocalReviewServer:
    approvals = PersonalApprovals(config)
    with quiet_private_runtime():
        entries = {
            approvals.reference(item): (item, metadata)
            for item, metadata in discovery(config, transport, OperationalMetrics())
        }

    def application(method: str, path: str, body: Any):
        if method == "GET" and path == "/api/catalog":
            return json_response(
                {
                    "entries": [
                        {
                            "id": reference,
                            **metadata,
                            "format": item.format,
                            "size": item.size,
                            "decision": approvals.decisions.get(reference, "UNREVIEWED"),
                            "needs_review": approvals.review.get(reference, []),
                        }
                        for reference, (item, metadata) in entries.items()
                    ]
                }
            )
        if (
            method == "POST"
            and path == "/api/approve"
            and isinstance(body, dict)
            and set(body) == {"id", "decision", "attest_personal"}
        ):
            reference = body["id"]
            if (
                not isinstance(reference, str)
                or reference not in entries
                or type(body["attest_personal"]) is not bool
            ):
                raise PrivateError("ANNOTATION_INVALID")
            approvals.decide(
                entries[reference][0], body["decision"], attest_personal=body["attest_personal"]
            )
            return json_response({"saved": True})
        return json_response({"error": "REQUEST_REJECTED"}, 404)

    html = (
        """<!doctype html><html lang="en"><meta charset="utf-8"><title>Local personal attachment review</title><style>body{font:16px system-ui;max-width:1050px;margin:35px auto;padding:0 20px;background:#f5f7fa;color:#152435}.card{background:white;border:1px solid #ced8e2;border-radius:10px;padding:20px;margin:15px 0}h1{font-size:26px}.detail{white-space:pre-wrap;overflow-wrap:anywhere}button{padding:9px;margin:8px 8px 0 0}.warning{background:#fff2cd;padding:15px}#message{color:#963b15}</style><h1>Personal attachment review</h1><p class="warning">Private metadata is visible only in this local browser. An allowed sender does not establish that an attachment is personal. Exclude employer, corporate, forwarded work material, or anything uncertain. No attachment bytes are downloaded here.</p><p id="message"></p><main id="entries"></main><script nonce="__NONCE__">"""
        + browser_script()
        + """async function load(){const data=await(await api('/api/catalog')).json();const root=document.getElementById('entries');root.replaceChildren();for(const entry of data.entries){const card=document.createElement('section');card.className='card';const details=document.createElement('div');details.className='detail';details.textContent='Subject: '+entry.subject+'\\nSender: '+entry.sender+'\\nFilename: '+entry.filename+'\\nType: '+entry.format+' | Bytes: '+entry.size+'\\nDecision: '+entry.decision+' | Review: '+entry.needs_review.join(', ');card.append(details);const consent=document.createElement('label');const check=document.createElement('input');check.type='checkbox';consent.append(check,document.createTextNode(' I inspected the provenance and explicitly attest this attachment is personal, unrelated to any employer, and authorized for local processing.'));card.append(document.createElement('br'),consent);for(const decision of ['PERSONAL','EXCLUDE']){const button=document.createElement('button');button.textContent=decision==='PERSONAL'?'Approve this personal attachment':'Exclude';button.onclick=async()=>{try{if(decision==='PERSONAL'&&!check.checked)return;await api('/api/approve',{id:entry.id,decision,attest_personal:check.checked});await load();}catch(e){showError();}};card.append(button);}root.append(card);}}load().catch(showError);</script></html>"""
    )
    return LocalReviewServer(html, application)


def serve_personal_review(config: PrivateConfig, transport: GmailTransport) -> None:
    require_external_terminal(True)
    root = secure_directory(config.private_root)
    with quiet_private_runtime():
        server = review_server(config, transport)
        serve(server, root)
