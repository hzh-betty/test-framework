"""把结果中已记录的截图复制到报告目录，不改源文件或执行结果。"""

from pathlib import Path
from uuid import uuid4


def copy_screenshots(original, safe_result, output_dir: str | Path) -> None:
    output = Path(output_dir)
    copied = {}

    def visit(source_result, target_result):
        if hasattr(source_result, "attachments"):
            attachments = []
            for index, attachment in enumerate(source_result.attachments):
                if attachment.get("type") != "image/png":
                    continue
                source = Path(attachment.get("source", "")).resolve()
                if not source.is_file():
                    continue
                name = copied.get(source)
                if name is None:
                    image = source.read_bytes()
                    if not image.startswith(b"\x89PNG\r\n\x1a\n"):
                        continue
                    output.mkdir(parents=True, exist_ok=True)
                    name = f"{uuid4()}-attachment.png"
                    (output / name).write_bytes(image)
                    copied[source] = name
                attachments.append({"name": target_result.attachments[index].get("name", "截图"),
                                    "source": name, "type": "image/png"})
            target_result.attachments = attachments
        for field in ("setup_steps", "teardown_steps", "step_results", "steps", "children",
                      "case_results", "attempts", "suite_results"):
            for source_child, target_child in zip(getattr(source_result, field, []), getattr(target_result, field, [])):
                visit(source_child, target_child)

    visit(original, safe_result)
