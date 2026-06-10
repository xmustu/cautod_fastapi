from __future__ import annotations

import asyncio
import json
import logging
import threading
import shutil
from datetime import datetime
from pathlib import Path
logger = logging.getLogger(__name__)

try:
    import pythoncom
    import win32com.client as win32
except Exception:  # pragma: no cover
    pythoncom = None
    win32 = None

_sw_export_lock = threading.Lock()


def _export_slddoc_to_stl(sld_doc_path: str, stl_path: str) -> bool:
    """
    用 SolidWorks COM 导出 STL。
    - sld_doc_path: .SLDPRT 或 .SLDASM 的绝对路径
    - stl_path: 目标 .stl 绝对路径
    """
    if win32 is None or pythoncom is None:
        raise RuntimeError("缺少 pywin32 依赖：需要 win32com/pythoncom")

    sld_doc_path = str(sld_doc_path)
    stl_path = str(stl_path)

    sld_file = Path(sld_doc_path)
    if not sld_file.is_file():
        raise FileNotFoundError(f"SLD 文档不存在: {sld_doc_path}")

    sld_ext = Path(sld_doc_path).suffix.lower()
    if sld_ext == ".sldprt":
        doc_type = 1  # swDocPART
    elif sld_ext == ".sldasm":
        doc_type = 2  # swDocASSEMBLY
    else:
        raise ValueError(f"不支持的 SolidWorks 文档类型: {sld_ext}")

    # OpenDoc6 / SaveAs3 都不建议并发
    # SolidWorks COM 有时需要显式初始化线程
    if pythoncom is not None:
        pythoncom.CoInitialize()

    with _sw_export_lock:
        # 优先复用已存在的 SolidWorks 实例；否则再创建
        # 注意：不同 SW 版本/注册方式下，ProgID 大小写可能影响表现
        try:
            sw_app = win32.GetActiveObject("SldWorks.Application")
        except Exception:
            try:
                sw_app = win32.GetActiveObject("sldworks.application")
            except Exception:
                try:
                    sw_app = win32.Dispatch("SldWorks.Application")
                except Exception:
                    sw_app = win32.Dispatch("sldworks.application")

        # 为了提高 OpenDoc6 稳定性，导出阶段尽量可见/已就绪
        try:
            sw_app.Visible = True
        except Exception:
            pass

        # 参考 SolidWorks SaveAs3 签名：Errors/Warns 需要 ByRef int
        arg_Long_error = win32.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        arg_Long_warning = win32.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)

        def _try_open(open_options: int):
            err = win32.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warn = win32.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            doc_obj = sw_app.OpenDoc6(
                sld_doc_path,
                doc_type,
                open_options,
                "",
                err,
                warn,
            )
            err_val = getattr(err, "value", err)
            warn_val = getattr(warn, "value", warn)
            return doc_obj, err_val, warn_val

        # OpenDoc6 在 SolidWorks 刚启动/加载中时可能返回 None
        # 因此做短暂重试；先静默打开，再非静默兜底
        last_err = err_val = 0
        last_warn = warn_val = 0
        doc = None

        import time
        for attempt in range(3):
            doc, err_val, warn_val = _try_open(open_options=1)
            if doc is not None:
                break
            last_err, last_warn = err_val, warn_val
            time.sleep(1.0 + attempt * 0.5)

        if doc is None:
            print(
                f"[stl export] OpenDoc6 failed (after retries): "
                f"sld={sld_doc_path} open_options=1 err={err_val} warn={warn_val} size={sld_file.stat().st_size}"
            )
            # 再尝试非静默
            doc, err_val, warn_val = _try_open(open_options=0)
            if doc is None:
                raise RuntimeError(
                    f"SolidWorks 打开文档失败: {sld_doc_path} (err={err_val}, warn={warn_val})"
                )

        # SaveAs3 对 STL 导出：关键是 ExportData/AdvancedSaveAsOptions 类型要匹配
        # 按 PySolidworksClass.py 的写法：传入 VT_DISPATCH 的 Nothing Variant
        arg_Nothing = win32.VARIANT(pythoncom.VT_DISPATCH, None)

        try:
            doc.ClearSelection2(True)
        except Exception:
            pass

        ok = doc.Extension.SaveAs3(
            stl_path,
            0,  # swSaveAsCurrentVersion
            1,  # swSaveAsOptions_Silent
            arg_Nothing,  # ExportData
            arg_Nothing,  # AdvancedSaveAsOptions
            arg_Long_error,
            arg_Long_warning,
        )

        # 尽量关闭文档，避免堆积
        try:
            sw_app.CloseDoc(sld_doc_path)
        except Exception:
            pass

    # SaveAs3 成功与否还要看文件是否真的生成
    stl_file = Path(stl_path)
    ok_file = stl_file.is_file() and stl_file.stat().st_size > 0
    if not ok_file:
        err_val = getattr(arg_Long_error, "value", arg_Long_error)
        warn_val = getattr(arg_Long_warning, "value", arg_Long_warning)
        raise RuntimeError(f"SaveAs3 导出 STL 失败：ok={ok} err={err_val} warn={warn_val}")
    return True

from apps.providers.agent_client import AgentServiceClient
from apps.providers.geometry_provider import (
    resolve_agent_service_base_url,
    resolve_agent_version,
)
from apps.routes.chat import save_or_update_message_in_redis
from apps.streaming_redis import aclose_streaming_redis, create_streaming_redis
from apps.schemas import (
    GenerationMetadata,
    Message,
    SSEConversationInfo,
    SSEImageChunk,
    SSEResponse,
    SSETextChunk,
    TaskExecuteRequest,
)
from apps.task_utils import cancel_task_execution, check_task_terminated
from config import settings
from database.models import GeometryResults, Tasks


async def geometry_agent_stream_generator(
    http_request,
    request: TaskExecuteRequest,
    current_user,
    redis_client,
    combinde_query: str,
    task: Tasks,
):
    stream_redis = create_streaming_redis()
    _ = redis_client  # 保留参数以兼容调用方；流式内使用当前事件循环绑定的 Redis
    assistant_message = Message(
        role="assistant",
        content="",
        timestamp=datetime.now(),
        parts=[],
        metadata={},
        status="in_progress",
    )

    try:
        solidworks_pipeline_result: dict | None = None
        await save_or_update_message_in_redis(
            user_id=current_user.user_id,
            task_id=request.task_id,
            task_type=request.task_type,
            conversation_id=request.conversation_id,
            message=assistant_message,
            redis_client=stream_redis,
        )

        conversation_info_data = SSEConversationInfo(
            conversation_id=request.conversation_id, task_id=str(request.task_id)
        )
        yield f"event: conversation_info\ndata: {conversation_info_data.model_dump_json()}\n\n"

        full_answer: list[str] = []
        agent_version = resolve_agent_version(
            getattr(request, "provider", None),
            getattr(request, "version", None),
        )
        agent_base_url = resolve_agent_service_base_url(agent_version)
        client = AgentServiceClient(base_url=agent_base_url)
        session_id = task.dify_conversation_id

        async for payload in client.chat_stream(message=combinde_query, session_id=session_id):
            if await http_request.is_disconnected():
                await cancel_task_execution(
                    task,
                    stream_redis,
                    reason="page_leave",
                    mode="graceful",
                    actor_user_id=current_user.user_id,
                )
                break

            if await check_task_terminated(stream_redis, request.task_id):
                assistant_message.content += "\n\n**任务已被用户终止**"
                assistant_message.status = "cancelled"
                assistant_message.timestamp = datetime.now()
                await save_or_update_message_in_redis(
                    user_id=current_user.user_id,
                    task_id=request.task_id,
                    task_type=request.task_type,
                    conversation_id=request.conversation_id,
                    message=assistant_message,
                    redis_client=stream_redis,
                )
                task.status = "cancelled"
                await task.save()
                yield f"event: cancelled\ndata: {json.dumps({'task_id': str(request.task_id), 'message': '任务已被用户终止'})}\n\n"
                break

            event_type = payload.get("type")
            if event_type == "delta":
                chunk = str(payload.get("content", ""))
                if not chunk:
                    continue
                assistant_message.content += chunk
                assistant_message.timestamp = datetime.now()
                full_answer.append(chunk)
                text_chunk_data = SSETextChunk(text=chunk.replace("\\n", "\n"))
                yield f"event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n"
                await save_or_update_message_in_redis(
                    user_id=current_user.user_id,
                    task_id=request.task_id,
                    task_type=request.task_type,
                    conversation_id=request.conversation_id,
                    message=assistant_message,
                    redis_client=stream_redis,
                )
            elif event_type == "status":
                status_msg = str(payload.get("message", "")).strip()
                if status_msg:
                    text_chunk_data = SSETextChunk(text=f"\n{status_msg}\n")
                    yield f"event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n"
            elif event_type == "error":
                raise RuntimeError(str(payload.get("error", "agent service error")))
            elif event_type == "pipeline_result":
                # solidworks_agent 在完成时透传 model_file/code_file 路径
                solidworks_pipeline_result = payload
            elif event_type == "done":
                break

            maybe_session_id = payload.get("session_id")
            if maybe_session_id and task.dify_conversation_id != maybe_session_id:
                task.dify_conversation_id = maybe_session_id
                await task.save()

        # 先尝试用 solidworks_agent 的透传结果落库/拷贝到 /files 目录
        geometry_result = await GeometryResults.get_or_none(task_id=task.task_id)
        if solidworks_pipeline_result:
            req_type = solidworks_pipeline_result.get("request_type")

            if req_type == "part":
                model_file = solidworks_pipeline_result.get("model_file")
                code_file = solidworks_pipeline_result.get("code_file")
                if model_file and code_file:
                    base_dir = Path(settings.DIRECTORY) if settings.DIRECTORY else Path("files")
                    task_dir = base_dir / str(request.conversation_id) / str(task.task_id)
                    task_dir.mkdir(parents=True, exist_ok=True)

                    model_dest = task_dir / Path(str(model_file)).name
                    code_dest = task_dir / Path(str(code_file)).name

                    if Path(str(model_file)).is_file():
                        shutil.copy2(str(model_file), str(model_dest))
                    if Path(str(code_file)).is_file():
                        shutil.copy2(str(code_file), str(code_dest))

                    # 仅导出一个“整体 STL”给前端：model.stl
                    stl_dest = task_dir / "model.stl"
                    try:
                        if stl_dest.exists():
                            try:
                                stl_dest.unlink()
                            except Exception:
                                pass
                        ok = _export_slddoc_to_stl(str(model_dest), str(stl_dest))
                        if not ok:
                            print(f"[stl export failed] model_dest={model_dest} stl_dest={stl_dest}")
                    except Exception as e:
                        # 回退：尝试从 solidworks_agent 输出的源文件导出（避免拷贝导致的异常）
                        print(f"[stl export exception] model_dest={model_dest} stl_dest={stl_dest} err={e}; try source model_file")
                        try:
                            ok = _export_slddoc_to_stl(str(model_file), str(stl_dest))
                            if not ok:
                                print(f"[stl export failed] source model_file={model_file} stl_dest={stl_dest}")
                        except Exception as e2:
                            print(
                                f"[stl export exception] source model_file={model_file} stl_dest={stl_dest} err={e2}"
                            )
                        # 导出失败不阻塞主流程；前端会基于是否存在 model.stl 决定展示

                    update_data = {
                        "cad_file_path": str(model_dest),
                        "code_file_path": str(code_dest),
                        "preview_image_path": None,
                    }

                    if geometry_result:
                        await geometry_result.update_from_dict(update_data).save()
                    else:
                        geometry_result = await GeometryResults.create(task_id=task.task_id, **update_data)
                        await geometry_result.save()

            elif req_type == "assembly":
                assembly_model_file = solidworks_pipeline_result.get("assembly_model_file")
                assembly_code_file = solidworks_pipeline_result.get("assembly_code_file")
                parts = solidworks_pipeline_result.get("parts") or []

                if assembly_model_file and assembly_code_file:
                    base_dir = Path(settings.DIRECTORY) if settings.DIRECTORY else Path("files")
                    task_dir = base_dir / str(request.conversation_id) / str(task.task_id)
                    task_dir.mkdir(parents=True, exist_ok=True)

                    # 1) 先拷贝 assembly 主文件到 task_dir
                    assembly_model_dest = task_dir / Path(str(assembly_model_file)).name
                    assembly_code_dest = task_dir / Path(str(assembly_code_file)).name

                    if Path(str(assembly_model_file)).is_file():
                        shutil.copy2(str(assembly_model_file), str(assembly_model_dest))
                    if Path(str(assembly_code_file)).is_file():
                        shutil.copy2(str(assembly_code_file), str(assembly_code_dest))

                    # 2) 顺带拷贝每个 part 的产物（便于后续前端下载/排错）
                    for p in parts:
                        mf = p.get("model_file")
                        cf = p.get("code_file")
                        if mf and Path(str(mf)).is_file():
                            dest = task_dir / Path(str(mf)).name
                            shutil.copy2(str(mf), str(dest))
                        if cf and Path(str(cf)).is_file():
                            dest = task_dir / Path(str(cf)).name
                            shutil.copy2(str(cf), str(dest))

                    update_data = {
                        "cad_file_path": str(assembly_model_dest),
                        "code_file_path": str(assembly_code_dest),
                        "preview_image_path": None,
                    }

                    if geometry_result:
                        await geometry_result.update_from_dict(update_data).save()
                    else:
                        geometry_result = await GeometryResults.create(task_id=task.task_id, **update_data)
                        await geometry_result.save()

                    # 导出“整体 STL”给前端：model.stl
                    stl_dest = task_dir / "model.stl"
                    try:
                        if stl_dest.exists():
                            try:
                                stl_dest.unlink()
                            except Exception:
                                pass
                        ok = _export_slddoc_to_stl(str(assembly_model_dest), str(stl_dest))
                        if not ok:
                            print(f"[stl export failed] assembly_model_dest={assembly_model_dest} stl_dest={stl_dest}")
                    except Exception as e:
                        print(
                            f"[stl export exception] assembly_model_dest={assembly_model_dest} stl_dest={stl_dest} err={e}; try source assembly_model_file"
                        )
                        try:
                            ok = _export_slddoc_to_stl(str(assembly_model_file), str(stl_dest))
                            if not ok:
                                print(
                                    f"[stl export failed] source assembly_model_file={assembly_model_file} stl_dest={stl_dest}"
                                )
                        except Exception as e2:
                            print(
                                f"[stl export exception] source assembly_model_file={assembly_model_file} stl_dest={stl_dest} err={e2}"
                            )

        geometry_result = await GeometryResults.get_or_none(task_id=task.task_id)
        if geometry_result:
            cad_file_name = Path(geometry_result.cad_file_path).name if geometry_result.cad_file_path else None
            code_file_name = Path(geometry_result.code_file_path).name if geometry_result.code_file_path else None
            preview_file_name = (
                Path(geometry_result.preview_image_path).name if geometry_result.preview_image_path else None
            )

            # 约定：前端展示只需要一个整体 STL：files/{conversation_id}/{task_id}/model.stl
            base_dir = Path(settings.DIRECTORY) if settings.DIRECTORY else Path("files")
            task_dir = base_dir / str(request.conversation_id) / str(task.task_id)
            stl_path = task_dir / "model.stl"
            stl_file_name = "model.stl" if stl_path.is_file() else None

            final_metadata = GenerationMetadata(
                cad_file=cad_file_name,
                stl_file=stl_file_name,
                code_file=code_file_name,
                preview_image=preview_file_name,
            )

            # 仅当预览图存在时才推送 image_chunk
            if preview_file_name:
                base_dir = settings.STATIC_URL if settings.STATIC_URL else "/files"
                image_url = f"{base_dir}/{request.conversation_id}/{request.task_id}/{preview_file_name}"
                image_part = {
                    "type": "image",
                    "imageUrl": image_url,
                    "fileName": preview_file_name,
                    "altText": "几何建模预览图",
                }
                assistant_message.parts.append(image_part)
                assistant_message.timestamp = datetime.now()
                image_chunk_data = SSEImageChunk(
                    imageUrl=image_url, fileName=preview_file_name, altText="几何建模预览图"
                )
                yield f"event: image_chunk\ndata: {image_chunk_data.model_dump_json()}\n\n"
                await save_or_update_message_in_redis(
                    user_id=current_user.user_id,
                    task_id=request.task_id,
                    task_type=request.task_type,
                    conversation_id=request.conversation_id,
                    message=assistant_message,
                    redis_client=stream_redis,
                )

            assistant_message.metadata = final_metadata.model_dump()
        else:
            final_metadata = GenerationMetadata(cad_file=None, code_file=None, stl_file=None, preview_image=None)
            assistant_message.metadata = final_metadata.model_dump()

        final_response_data = SSEResponse(
            answer="".join(full_answer),
            suggested_questions=None,
            metadata=final_metadata,
        )
        yield f"event: message_end\ndata: {final_response_data.model_dump_json()}\n\n"

        assistant_message.status = "done"
        assistant_message.timestamp = datetime.now()
        await save_or_update_message_in_redis(
            user_id=current_user.user_id,
            task_id=request.task_id,
            task_type=request.task_type,
            conversation_id=request.conversation_id,
            message=assistant_message,
            redis_client=stream_redis,
        )
        task.status = "done"
        await task.save()
    except Exception as e:
        logger.exception(
            "geometry_agent_stream_failed task_id=%s conversation_id=%s",
            getattr(request, "task_id", None),
            getattr(request, "conversation_id", None),
        )
        task.status = "failed"
        await task.save()
        assistant_message.content += f"\n\n**任务执行出错**: {e}"
        assistant_message.status = "failed"
        assistant_message.timestamp = datetime.now()
        await save_or_update_message_in_redis(
            user_id=current_user.user_id,
            task_id=request.task_id,
            task_type=request.task_type,
            conversation_id=request.conversation_id,
            message=assistant_message,
            redis_client=stream_redis,
        )
        yield f"event: error\ndata: {json.dumps({'error': 'An error occurred during task execution.'})}\n\n"
    finally:
        await aclose_streaming_redis(stream_redis)

