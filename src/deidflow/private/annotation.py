"""Opt-in private localhost annotation; never invoked on private data by Codex."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import math
import secrets
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .gmail import strict_json
from .runner import quiet_private_runtime
from .security import (
    PrivateArgumentParser,
    PrivateError,
    private_path,
    protect,
    require_external_terminal,
    secure_directory,
    write_private,
)
from .web import LocalReviewServer, browser_script, json_response, serve

_EXTENSIONS = {
    ".txt",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".pdf",
    ".docx",
    ".xlsx",
    ".parquet",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
}
_STATUSES = {"CONFIRMED", "MISSED", "FALSE_POSITIVE", "OCR_ERROR"}


class AnnotationStore:
    """Only annotation geometry/labels persist by default, never original excerpts."""

    def __init__(
        self,
        source_dir: Path,
        private_root: Path,
        engine: Any,
        *,
        consent_display: bool = False,
        allow_store_excerpts: bool = False,
        max_documents: int = 100,
        max_bytes: int = 64 * 1024**2,
    ) -> None:
        if consent_display is not True:
            raise PrivateError("ANNOTATION_CONSENT_REQUIRED")
        if (
            type(max_documents) is not int
            or not 1 <= max_documents <= 1000
            or type(max_bytes) is not int
            or not 1 <= max_bytes <= 64 * 1024**2
        ):
            raise PrivateError("ANNOTATION_INVALID")
        self.source_dir = private_path(source_dir)
        self.root = secure_directory(private_root)
        if self.source_dir == self.root or not self.source_dir.is_dir():
            raise PrivateError("PRIVATE_PATH_REQUIRED")
        self.records = secure_directory(self.root / "annotations")
        self.engine, self.allow_store_excerpts, self.max_bytes = (
            engine,
            allow_store_excerpts,
            max_bytes,
        )
        key = self.root / ".annotation-key"
        if not key.exists():
            write_private(key, secrets.token_bytes(32))
        protect(key, directory=False)
        secret = key.read_bytes()
        if len(secret) != 32:
            raise PrivateError("PRIVATE_CONFIG_INVALID")
        self.sources: dict[str, Path] = {}
        for path in sorted(self.source_dir.iterdir()):
            if len(self.sources) >= max_documents:
                break
            if (
                path.is_symlink()
                or not path.is_file()
                or path.suffix.lower() not in _EXTENSIONS
                or path.stat().st_size > max_bytes
            ):
                continue
            identity = hmac.new(
                secret, str(path.resolve()).encode("utf-8"), hashlib.sha256
            ).hexdigest()
            self.sources[identity] = path

    def _path(self, identity: str) -> Path:
        if not isinstance(identity, str) or identity not in self.sources:
            raise PrivateError("ANNOTATION_INVALID")
        source = private_path(self.sources[identity])
        if source.parent != self.source_dir:
            raise PrivateError("PRIVATE_PATH_REQUIRED")
        return source

    def fingerprint(self, identity: str) -> str:
        path = self._path(identity)
        if path.stat().st_size > self.max_bytes:
            raise PrivateError("PRIVATE_LIMIT_EXCEEDED")
        with path.open("rb") as handle:
            digest, total = hashlib.sha256(), 0
            while chunk := handle.read(1024 * 1024):
                total += len(chunk)
                if total > self.max_bytes:
                    raise PrivateError("PRIVATE_LIMIT_EXCEEDED")
                digest.update(chunk)
        return digest.hexdigest()

    def catalog(self) -> list[dict[str, str]]:
        return [
            {"id": identity, "format": path.suffix.lower().lstrip(".")}
            for identity, path in self.sources.items()
        ]

    def describe(self, identity: str) -> dict[str, Any]:
        source = self._path(identity)
        digest = self.fingerprint(identity)
        with quiet_private_runtime():
            graph = self.engine.read(source)
            fragments = []
            for i, fragment in enumerate(graph.fragments):
                found = (
                    self.engine.scan_ocr_text(fragment.text)
                    if fragment.kind == "ocr"
                    else self.engine.scan_text(fragment.text)
                )
                fragments.append(
                    {
                        "id": str(i),
                        "kind": fragment.kind,
                        "text": fragment.text,
                        "page": fragment.location.page,
                        "row": fragment.location.row,
                        "column": fragment.location.column,
                        "cell": fragment.location.cell,
                        "findings": [
                            {"start": f.start, "end": f.end, "entity_type": f.entity_type}
                            for f in found
                        ],
                    }
                )
        if self.fingerprint(identity) != digest:
            raise PrivateError("SOURCE_CHANGED")
        pages = int(
            graph.metadata.get(
                "page_count", max((f.location.page or 0 for f in graph.fragments), default=0)
            )
        )
        if source.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"} and not pages:
            from PIL import Image

            with Image.open(source) as image:
                pages = int(getattr(image, "n_frames", 1))
        return {
            "id": identity,
            "source_sha256": digest,
            "format": source.suffix.lower().lstrip("."),
            "pages": pages,
            "fragments": fragments,
            "complete": graph.complete,
            "annotations": self.load(identity),
        }

    def load(self, identity: str) -> list[dict[str, Any]]:
        self._path(identity)
        path = self.records / (identity + ".json")
        if not path.exists():
            return []
        if path.stat().st_size > 2 * 1024**2:
            raise PrivateError("ANNOTATION_INVALID")
        data = strict_json(path.read_text(encoding="utf-8"))
        if (
            not isinstance(data, dict)
            or set(data)
            != {
                "schema_version",
                "document_id",
                "source_sha256",
                "excerpts_consented",
                "annotations",
            }
            or data["schema_version"] != 1
            or data["document_id"] != identity
            or not isinstance(data["annotations"], list)
        ):
            raise PrivateError("ANNOTATION_INVALID")
        if data["source_sha256"] != self.fingerprint(identity):
            raise PrivateError("SOURCE_CHANGED")
        return data["annotations"]

    def save(self, payload: dict[str, Any]) -> int:
        if (
            not isinstance(payload, dict)
            or set(payload) != {"document_id", "source_sha256", "store_excerpts", "annotations"}
            or type(payload["store_excerpts"]) is not bool
        ):
            raise PrivateError("ANNOTATION_INVALID")
        identity = payload["document_id"]
        if payload["store_excerpts"] and not self.allow_store_excerpts:
            raise PrivateError("ANNOTATION_CONSENT_REQUIRED")
        description = self.describe(identity)
        if payload["source_sha256"] != description["source_sha256"]:
            raise PrivateError("SOURCE_CHANGED")
        records = payload["annotations"]
        if not isinstance(records, list) or len(records) > 10000:
            raise PrivateError("ANNOTATION_INVALID")
        allowed = {
            "kind",
            "entity_type",
            "status",
            "fragment_id",
            "start",
            "end",
            "page",
            "bbox",
            "group_id",
            "corrected_text",
        }
        import re

        output = []
        for record in records:
            if (
                not isinstance(record, dict)
                or set(record) != allowed
                or not isinstance(record["kind"], str)
                or record["kind"] not in {"span", "region", "field"}
                or not isinstance(record["status"], str)
                or record["status"] not in _STATUSES
                or not isinstance(record["entity_type"], str)
                or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", record["entity_type"])
            ):
                raise PrivateError("ANNOTATION_INVALID")
            clean = dict(record)
            group = record["group_id"]
            if group is not None and (
                not isinstance(group, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", group)
            ):
                raise PrivateError("ANNOTATION_INVALID")
            correction = record["corrected_text"]
            if correction is not None and (
                not isinstance(correction, str) or len(correction) > 10000
            ):
                raise PrivateError("ANNOTATION_INVALID")
            if correction and (not self.allow_store_excerpts or not payload["store_excerpts"]):
                raise PrivateError("ANNOTATION_CONSENT_REQUIRED")
            if record["kind"] in {"span", "field"}:
                fragment_id = record["fragment_id"]
                if (
                    not isinstance(fragment_id, str)
                    or not fragment_id.isdecimal()
                    or int(fragment_id) >= len(description["fragments"])
                ):
                    raise PrivateError("ANNOTATION_INVALID")
                fragment = description["fragments"][int(fragment_id)]
                start, end = record["start"], record["end"]
                if (
                    type(start) is not int
                    or type(end) is not int
                    or not 0 <= start < end <= len(fragment["text"])
                ):
                    raise PrivateError("ANNOTATION_INVALID")
                if record["kind"] == "field" and (start != 0 or end != len(fragment["text"])):
                    raise PrivateError("ANNOTATION_INVALID")
                if record["bbox"] is not None or record["page"] is not None:
                    raise PrivateError("ANNOTATION_INVALID")
                if payload["store_excerpts"]:
                    clean["excerpt"] = fragment["text"][start:end]
            else:
                box, page = record["bbox"], record["page"]
                if (
                    type(page) is not int
                    or not 1 <= page <= description["pages"]
                    or record["fragment_id"] is not None
                    or record["start"] is not None
                    or record["end"] is not None
                ):
                    raise PrivateError("ANNOTATION_INVALID")
                if (
                    not isinstance(box, list)
                    or len(box) != 4
                    or not all(type(v) in {int, float} and math.isfinite(v) for v in box)
                    or not 0 <= box[0] < box[2] <= 1
                    or not 0 <= box[1] < box[3] <= 1
                ):
                    raise PrivateError("ANNOTATION_INVALID")
            output.append(clean)
        path = self.records / (identity + ".json")
        data = {
            "schema_version": 1,
            "document_id": identity,
            "source_sha256": description["source_sha256"],
            "excerpts_consented": payload["store_excerpts"],
            "annotations": output,
        }
        write_private(
            path, (json.dumps(data, ensure_ascii=True) + "\n").encode(), overwrite=path.exists()
        )
        return len(output)

    def render(self, identity: str, page_number: int) -> bytes:
        source = self._path(identity)
        if type(page_number) is not int or page_number < 1:
            raise PrivateError("ANNOTATION_INVALID")
        from PIL import Image

        if source.suffix.lower() == ".pdf":
            import pypdfium2 as pdfium

            from deidflow.pdf_runtime import PDFIUM_LOCK

            with PDFIUM_LOCK, pdfium.PdfDocument(source) as document:
                if page_number > len(document):
                    raise PrivateError("ANNOTATION_INVALID")
                page = document[page_number - 1]
                bitmap = None
                try:
                    width, height = page.get_size()
                    if width * height * 2.25 > 40_000_000:
                        raise PrivateError("PRIVATE_LIMIT_EXCEEDED")
                    bitmap = page.render(scale=1.5)
                    with bitmap.to_pil() as image:
                        return _png(image)
                finally:
                    if bitmap:
                        bitmap.close()
                    page.close()
        if source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            raise PrivateError("ANNOTATION_INVALID")
        with Image.open(source) as image:
            if (
                page_number > getattr(image, "n_frames", 1)
                or image.width * image.height > 40_000_000
            ):
                raise PrivateError("ANNOTATION_INVALID")
            image.seek(page_number - 1)
            return _png(image)

    def export_training(self, target: Path, *, consent_original_text: bool = False) -> int:
        if consent_original_text is not True:
            raise PrivateError("ANNOTATION_CONSENT_REQUIRED")
        target = private_path(target)
        rows = []
        for identity in self.sources:
            description = self.describe(identity)
            for fragment in description["fragments"]:
                spans = [
                    {"start": r["start"], "end": r["end"], "label": r["entity_type"]}
                    for r in description["annotations"]
                    if r["kind"] in {"span", "field"}
                    and r["fragment_id"] == fragment["id"]
                    and r["status"] in {"CONFIRMED", "MISSED"}
                ]
                if spans:
                    rows.append({"text": fragment["text"], "spans": spans})
        # Regions and OCR corrections remain in private sidecars. They are not
        # silently converted to token/span training labels with guessed offsets.
        write_private(
            target, "".join(json.dumps(row, ensure_ascii=True) + "\n" for row in rows).encode()
        )
        return len(rows)


def _png(image: Any) -> bytes:
    from PIL import Image

    with Image.new("RGB", image.size, "white") as clean, io.BytesIO() as buffer:
        clean.paste(image)
        clean.save(buffer, format="PNG")
        return buffer.getvalue()


def annotation_server(store: AnnotationStore) -> LocalReviewServer:
    def application(method: str, path: str, body: Any):
        parsed = urlsplit(path)
        query = parse_qs(parsed.query)
        if method == "GET" and parsed.path == "/api/catalog":
            return json_response(
                {"entries": store.catalog(), "allow_store_excerpts": store.allow_store_excerpts}
            )
        if method == "GET" and parsed.path == "/api/sample":
            return json_response(store.describe(query.get("id", [""])[0]))
        if method == "GET" and parsed.path == "/api/image":
            return (
                200,
                store.render(query.get("id", [""])[0], int(query.get("page", ["1"])[0])),
                "image/png",
            )
        if method == "POST" and parsed.path == "/api/annotations":
            return json_response({"saved": store.save(body)})
        return json_response({"error": "REQUEST_REJECTED"}, 404)

    return LocalReviewServer(
        _HTML_PREFIX + browser_script() + _OFFSET_SCRIPT + _SCRIPT + "</script></html>", application
    )


_OFFSET_SCRIPT = r"""function sourceOffset(source,displayed,utf16Index){const end=Array.from(displayed.slice(0,utf16Index)).length;const original=Array.from(source);let i=0,n=0;while(i<original.length&&n<end){if(original[i]==='\r'&&original[i+1]==='\n')i+=2;else i++;n++;}return i;}"""

_HTML_PREFIX = """<!doctype html><html lang="en"><meta charset="utf-8"><title>Local private annotation</title><style>body{font:15px system-ui;max-width:1200px;margin:25px auto;padding:0 20px;background:#f6f8fa;color:#172d42}h1{font-size:25px}button,input,select{padding:7px;margin:4px}textarea{width:98%;height:210px;font:16px/1.5 monospace}section{background:white;padding:18px;border:1px solid #cad4df;border-radius:10px;margin:15px 0}.warning{padding:12px;background:#fff3ce}#canvas{max-width:100%;border:1px solid #8b9cad;touch-action:none}#records button{display:block;text-align:left;max-width:100%;overflow-wrap:anywhere}#message{color:#9a3c00}.row{display:flex;flex-wrap:wrap;gap:7px}</style><h1>Private local annotation</h1><p class="warning">Original content is displayed only because you explicitly consented. No upload endpoint or external synchronization exists. Annotation labels/offsets persist privately. Original excerpts and OCR corrections need additional consent.</p><div class="row"><label>Sample <select id="samples"></select></label><label>Fragment <select id="fragments"></select></label><label>Page <input id="page" type="number" min="1" value="1" style="width:70px"></label><button id="showImage">Show local raster</button></div><p id="message"></p><section><textarea id="text" readonly></textarea><p>Select text above, or draw a region on the local page image below.</p><canvas id="canvas" hidden></canvas></section><section><div class="row"><label>Kind <select id="kind"><option value="span">Text span</option><option value="field">Whole structured field</option><option value="region">PDF/image region</option></select></label><label>Entity <input id="entity" value="PERSON"></label><label>Review <select id="status"><option>CONFIRMED</option><option>MISSED</option><option>FALSE_POSITIVE</option><option>OCR_ERROR</option></select></label><label>Repeated mention group <input id="group"></label></div><div class="row"><label>Start <input id="start" type="number" min="0" value="0"></label><label>End <input id="end" type="number" min="1" value="1"></label></div><label>OCR correction (requires excerpt consent)<input id="correction" style="width:65%"></label><p><label><input id="storeExcerpts" type="checkbox"> I explicitly consent to storing original excerpts and typed OCR corrections in this private annotation dataset.</label></p><button id="add">Add/update annotation</button><button id="new">New annotation</button><button id="remove">Remove selected annotation</button><button id="save">Save private annotations</button></section><section><h2>Detector candidates</h2><div id="candidates"></div><h2>Reviewed annotations</h2><div id="records"></div></section><script nonce="__NONCE__">"""
_SCRIPT = """let current=null,records=[],selected=-1,box=null,image=null,anchor=null;const byId=id=>document.getElementById(id);function fragment(){return current.fragments[Number(byId('fragments').value)];}function textView(){byId('text').value=fragment()?.text||'';const root=byId('candidates');root.replaceChildren();for(const f of fragment()?.findings||[]){const button=document.createElement('button');button.textContent=f.entity_type+' '+f.start+':'+f.end;button.onclick=()=>{byId('start').value=f.start;byId('end').value=f.end;byId('entity').value=f.entity_type;byId('kind').value='span';};root.append(button);}}function draw(){if(!image)return;const canvas=byId('canvas'),ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);if(box){ctx.strokeStyle='#ef5a2d';ctx.lineWidth=3;ctx.strokeRect(box[0]*canvas.width,box[1]*canvas.height,(box[2]-box[0])*canvas.width,(box[3]-box[1])*canvas.height);}}function listRecords(){const root=byId('records');root.replaceChildren();records.forEach((record,index)=>{const button=document.createElement('button');button.textContent=(index+1)+' '+record.kind+' '+record.entity_type+' '+record.status+' '+(record.kind==='region'?'page '+record.page:record.start+':'+record.end);button.onclick=()=>{selected=index;byId('kind').value=record.kind;byId('entity').value=record.entity_type;byId('status').value=record.status;byId('group').value=record.group_id||'';byId('correction').value=record.corrected_text||'';byId('start').value=record.start||0;byId('end').value=record.end||1;if(record.fragment_id!==null){byId('fragments').value=record.fragment_id;textView();}if(record.page)byId('page').value=record.page;box=record.bbox;draw();};root.append(button);});}async function loadSample(){current=await(await api('/api/sample?id='+encodeURIComponent(byId('samples').value))).json();records=current.annotations.map(({excerpt,...rest})=>rest);selected=-1;byId('fragments').replaceChildren();for(const f of current.fragments){const option=document.createElement('option');option.value=f.id;option.textContent='Fragment '+f.id+' ('+f.kind+')';byId('fragments').append(option);}byId('page').max=current.pages||1;byId('canvas').hidden=true;image=null;box=null;textView();listRecords();}byId('samples').onchange=()=>loadSample().catch(showError);byId('fragments').onchange=textView;byId('text').onselect=()=>{const input=byId('text');byId('start').value=sourceOffset(fragment().text,input.value,input.selectionStart);byId('end').value=sourceOffset(fragment().text,input.value,input.selectionEnd);};byId('showImage').onclick=async()=>{try{const response=await api('/api/image?id='+encodeURIComponent(current.id)+'&page='+byId('page').value);const url=URL.createObjectURL(await response.blob());image=new Image();image.onload=()=>{const c=byId('canvas');c.width=image.naturalWidth;c.height=image.naturalHeight;c.hidden=false;draw();URL.revokeObjectURL(url);};image.src=url;}catch(e){showError();}};function point(event){const r=byId('canvas').getBoundingClientRect();return[Math.max(0,Math.min(1,(event.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(event.clientY-r.top)/r.height))];}byId('canvas').onpointerdown=e=>{anchor=point(e);byId('canvas').setPointerCapture(e.pointerId);};byId('canvas').onpointermove=e=>{if(!anchor)return;const p=point(e);box=[Math.min(anchor[0],p[0]),Math.min(anchor[1],p[1]),Math.max(anchor[0],p[0]),Math.max(anchor[1],p[1])];draw();};byId('canvas').onpointerup=()=>{anchor=null;byId('kind').value='region';};byId('add').onclick=()=>{const kind=byId('kind').value;let start=Number(byId('start').value),end=Number(byId('end').value);if(kind==='field'){start=0;end=Array.from(fragment().text).length;}const record={kind,entity_type:byId('entity').value,status:byId('status').value,fragment_id:kind==='region'?null:byId('fragments').value,start:kind==='region'?null:start,end:kind==='region'?null:end,page:kind==='region'?Number(byId('page').value):null,bbox:kind==='region'?box:null,group_id:byId('group').value||null,corrected_text:byId('correction').value||null};if(selected<0)records.push(record);else records[selected]=record;listRecords();};byId('new').onclick=()=>{selected=-1;box=null;byId('correction').value='';};byId('remove').onclick=()=>{if(selected>=0)records.splice(selected,1);selected=-1;listRecords();};byId('save').onclick=async()=>{try{const response=await(await api('/api/annotations',{document_id:current.id,source_sha256:current.source_sha256,store_excerpts:byId('storeExcerpts').checked,annotations:records})).json();byId('message').textContent='Saved '+response.saved+' private annotations.';}catch(e){showError();}};api('/api/catalog').then(r=>r.json()).then(async data=>{byId('storeExcerpts').disabled=!data.allow_store_excerpts;for(const entry of data.entries){const option=document.createElement('option');option.value=entry.id;option.textContent='Sample '+(byId('samples').options.length+1)+' ('+entry.format+')';byId('samples').append(option);}if(data.entries.length)await loadSample();}).catch(showError);"""


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(prog="deidflow annotate")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--external-terminal-ack", action="store_true")
    parser.add_argument("--consent-display-originals", action="store_true")
    parser.add_argument("--allow-store-excerpts", action="store_true")
    parser.add_argument("--export-training", type=Path)
    parser.add_argument("--consent-export-original-text", action="store_true")
    parser.add_argument("--ocr-executable", type=Path)
    parser.add_argument("--tessdata-dir", type=Path)
    try:
        args = parser.parse_args(argv)
        require_external_terminal(args.external_terminal_ack)
        from deidflow import DeidEngine

        ocr = None
        if args.ocr_executable:
            from deidflow.ocr import TesseractOCR

            ocr = TesseractOCR(executable=str(args.ocr_executable), tessdata_dir=args.tessdata_dir)
        store = AnnotationStore(
            args.source_dir,
            args.private_root,
            DeidEngine(ocr=ocr),
            consent_display=args.consent_display_originals,
            allow_store_excerpts=args.allow_store_excerpts,
        )
        if args.export_training:
            with quiet_private_runtime():
                count = store.export_training(
                    args.export_training, consent_original_text=args.consent_export_original_text
                )
            print(json.dumps({"status": "PRIVATE_TRAINING_EXPORT_CREATED", "records": count}))
        else:
            with quiet_private_runtime():
                serve(annotation_server(store), store.root)
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        code = error.code if isinstance(error, PrivateError) else "PRIVATE_OPERATION_FAILED"
        print(json.dumps({"status": "BLOCKED", "code": code}), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
