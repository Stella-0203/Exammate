import shutil
from pathlib import Path
from uuid import uuid4

from core.config import MATERIALS_DIR
from storage.db import get_connection
from parsers.material_parser import extract_material_text

def import_material(
    file_path: str | Path,
    course_id: int | None = None,
    exam_id: int | None = None,
    db_path: str | Path | None = None,
    materials_dir: str | Path | None = None,
) -> dict:
    """
    导入一份 TXT 学习资料。

    主要流程：
    1. 解析原始文件。
    2. 校验课程和考试关联。
    3. 复制原文件到应用资料目录。
    4. 将资料信息和提取文本写入数据库。
    5. 如果保存失败，清理已复制的文件。

    db_path 和 materials_dir 主要用于测试时指定临时路径。
    """
    source_path = Path(file_path)

    # 第一步：提取文本。
    # 文件不存在、格式不支持或编码无法识别时，会直接抛出异常。
    #extracted_text = extract_txt_text(source_path)
    extracted_text = extract_material_text(source_path)

    if not extracted_text.strip():
        raise ValueError("资料内容为空，无法导入。")

    # 第二步：检查课程和考试是否存在，以及两者是否匹配。
    connection = get_connection(db_path)
    stored_path = None

    try:
        if course_id is not None:
            course = connection.execute(
                "SELECT id FROM courses WHERE id = ?",
                (course_id,),
            ).fetchone()

            if course is None:
                raise ValueError(f"课程不存在，course_id={course_id}")

        exam = None

        if exam_id is not None:
            exam = connection.execute(
                """
                SELECT id, course_id
                FROM exam_goals
                WHERE id = ?
                """,
                (exam_id,),
            ).fetchone()

            if exam is None:
                raise ValueError(f"考试目标不存在，exam_id={exam_id}")

            # 如果指定了考试但没有指定课程，则自动关联考试所属课程。
            if course_id is None:
                course_id = exam["course_id"]

            # 如果同时指定课程和考试，必须确保二者属于同一课程。
            elif course_id != exam["course_id"]:
                raise ValueError("指定的课程与考试目标不匹配。")

        # 第三步：生成安全且不容易重复的存储文件名。
        target_dir = (
            Path(materials_dir)
            if materials_dir is not None
            else MATERIALS_DIR
        )
        target_dir.mkdir(parents=True, exist_ok=True)

        #stored_name = f"{uuid4().hex}.txt"
        stored_name = f"{uuid4().hex}{source_path.suffix.lower()}"
        destination = target_dir / stored_name

        # 复制原文件，不影响用户的源文件。
        stored_path = str(destination.resolve())
        shutil.copy2(source_path, destination)

        # 第四步：保存资料记录。
        cursor = connection.execute(
            """
            INSERT INTO materials (
                course_id,
                exam_id,
                original_name,
                stored_path,
                file_type,
                extracted_text,
                parse_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                course_id,
                exam_id,
                source_path.name,
                stored_path,
                #"txt",
                source_path.suffix.lower().lstrip("."),
                extracted_text,
                "success",
            ),
        )

        material_id = cursor.lastrowid
        connection.commit()

        return {
            "id": material_id,
            "course_id": course_id,
            "exam_id": exam_id,
            "original_name": source_path.name,
            "stored_path": stored_path,
            #"file_type": "txt",
            "file_type": source_path.suffix.lower().lstrip("."),
            "extracted_text": extracted_text,
            "parse_status": "success",
        }

    except Exception:
        connection.rollback()

        # 如果数据库保存失败，删除本次复制的文件。
        if stored_path is not None:
            try:
                Path(stored_path).unlink(missing_ok=True)
            except OSError:
                # 不覆盖原始异常；文件清理问题由后续日志机制处理。
                pass

        raise

    finally:
        connection.close()



def list_materials(
    course_id: int | None = None,
    exam_id: int | None = None,
    db_path: str | Path | None = None,
) -> list[dict]:
    """查询资料列表，可按课程和考试筛选。"""
    connection = get_connection(db_path)

    try:
        sql = """
            SELECT
                id,
                course_id,
                exam_id,
                original_name,
                file_type,
                parse_status,
                created_at
            FROM materials
            WHERE 1 = 1
        """
        params = []

        if course_id is not None:
            sql += " AND course_id = ?"
            params.append(course_id)

        if exam_id is not None:
            sql += " AND exam_id = ?"
            params.append(exam_id)

        sql += " ORDER BY created_at DESC, id DESC"

        rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_material(
    material_id: int,
    db_path: str | Path | None = None,
) -> dict | None:
    """查询单条资料，包含提取文本和文件存储路径。"""
    connection = get_connection(db_path)

    try:
        row = connection.execute(
            """
            SELECT
                id,
                course_id,
                exam_id,
                original_name,
                stored_path,
                file_type,
                extracted_text,
                parse_status,
                parse_error,
                created_at
            FROM materials
            WHERE id = ?
            """,
            (material_id,),
        ).fetchone()

        return dict(row) if row is not None else None

    finally:
        connection.close()



def delete_material(
    material_id: int,
    db_path: str | Path | None = None,
    materials_dir: str | Path | None = None,
) -> bool:
    """
    删除一条资料记录及其对应的应用内文件。

    返回：
    - True：删除成功。
    - False：资料记录不存在。

    如果文件路径不在资料存储目录内，则拒绝删除。
    如果数据库操作失败，会回滚记录变更并尝试恢复文件。
    """
    connection = get_connection(db_path)
    backup_path = None
    stored_path = None
    file_removed = False

    try:
        # 第一步：查找资料记录。
        row = connection.execute(
            """
            SELECT id, stored_path
            FROM materials
            WHERE id = ?
            """,
            (material_id,),
        ).fetchone()

        if row is None:
            return False

        # 第二步：校验文件路径，防止误删资料目录外的文件。
        root = (
            Path(materials_dir)
            if materials_dir is not None
            else MATERIALS_DIR
        ).resolve()

        stored_path = Path(row["stored_path"]).resolve()

        try:
            stored_path.relative_to(root)
        except ValueError:
            raise ValueError(
                "资料文件路径不在允许的资料存储目录内，拒绝删除。"
            )

        # 如果文件存在，必须是普通文件，不能是目录。
        if stored_path.exists() and not stored_path.is_file():
            raise ValueError("资料存储路径不是普通文件，拒绝删除。")

        # 第三步：先备份应用内文件，再删除原文件。
        # 若数据库操作失败，可尝试恢复。
        if stored_path.exists():
            backup_path = stored_path.parent / (
                f".delete-backup-{uuid4().hex}"
            )
            shutil.copy2(stored_path, backup_path)
            stored_path.unlink()
            file_removed = True

        # 第四步：删除数据库记录并提交。
        connection.execute(
            "DELETE FROM materials WHERE id = ?",
            (material_id,),
        )
        connection.commit()

        # 提交成功后，备份文件不再需要。
        if backup_path is not None:
            try:
                backup_path.unlink(missing_ok=True)
            except OSError:
                # 清理备份失败不应把已成功的删除操作报告为失败。
                pass

        return True

    except Exception:
        connection.rollback()

        # 数据库操作失败时，尝试恢复刚刚删除的文件。
        if (
            file_removed
            and backup_path is not None
            and stored_path is not None
        ):
            try:
                if backup_path.exists() and not stored_path.exists():
                    shutil.copy2(backup_path, stored_path)
                    backup_path.unlink(missing_ok=True)
            except OSError:
                # 保留备份文件，便于后续人工恢复。
                pass

        raise

    finally:
        connection.close()

