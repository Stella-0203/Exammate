import sqlite3
from pathlib import Path

from core.config import DB_PATH


def get_connection(
    db_path: str | Path | None = None,
) -> sqlite3.Connection:
    """创建数据库连接，默认使用项目正式数据库。"""
    path = Path(db_path) if db_path is not None else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection



def _migrate_review_plans_status(
    connection: sqlite3.Connection,
) -> None:
    """为已有的复习计划表增加 stale 状态，保留原有数据。"""
    row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'review_plans'
        """
    ).fetchone()

    if row is None:
        return

    table_sql = row["sql"] or ""

    # 已支持 stale，无需迁移。
    if "'stale'" in table_sql or '"stale"' in table_sql:
        return

    # 必须在事务开始前关闭外键检查，才能安全重建被任务表引用的父表。
    connection.execute("PRAGMA foreign_keys = OFF")

    try:
        connection.execute("BEGIN")

        connection.execute(
            """
            CREATE TABLE review_plans_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_id INTEGER NOT NULL,
                review_goal TEXT NOT NULL DEFAULT '',
                exam_date TEXT NOT NULL,
                daily_available_minutes INTEGER NOT NULL
                    CHECK (daily_available_minutes > 0),
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'archived', 'stale')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (exam_id)
                    REFERENCES exam_goals(id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            INSERT INTO review_plans_new (
                id, exam_id, review_goal, exam_date,
                daily_available_minutes, status,
                created_at, updated_at
            )
            SELECT
                id, exam_id, review_goal, exam_date,
                daily_available_minutes, status,
                created_at, updated_at
            FROM review_plans
            """
        )

        connection.execute("DROP TABLE review_plans")
        connection.execute(
            "ALTER TABLE review_plans_new RENAME TO review_plans"
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_review_plans_exam_id
            ON review_plans(exam_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_review_plans_status
            ON review_plans(status)
            """
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.execute("PRAGMA foreign_keys = ON")

    # 检查迁移后的外键是否仍然完整。
    violations = connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    if violations:
        raise RuntimeError(
            f"复习计划表迁移后发现外键问题：{violations}"
        )


def init_db(db_path: str | Path | None = None) -> None:
    """初始化 ExamMate 的基础数据库结构。"""
    connection = get_connection(db_path)

    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS exam_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                exam_date TEXT,
                raw_syllabus_text TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN (
                        'draft',
                        'needs_review',
                        'confirmed'
                    )),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (course_id)
                    REFERENCES courses(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS syllabus_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_id INTEGER NOT NULL,
                parent_id INTEGER,
                content TEXT NOT NULL,
                item_type TEXT NOT NULL DEFAULT 'other'
                    CHECK (item_type IN (
                        'knowledge',
                        'skill',
                        'question_type',
                        'other'
                    )),
                origin TEXT NOT NULL
                    CHECK (origin IN ('original', 'inferred')),
                review_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (review_status IN (
                        'pending',
                        'confirmed',
                        'edited',
                        'excluded'
                    )),
                rationale TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (exam_id)
                    REFERENCES exam_goals(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (parent_id)
                    REFERENCES syllabus_items(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_exam_goals_course_id
                ON exam_goals(course_id);

            CREATE INDEX IF NOT EXISTS idx_syllabus_items_exam_id
                ON syllabus_items(exam_id);

            CREATE INDEX IF NOT EXISTS idx_syllabus_items_parent_id
                ON syllabus_items(parent_id);
            
            
                        
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                course_id INTEGER,
                exam_id INTEGER,

                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                file_type TEXT NOT NULL,

                extracted_text TEXT NOT NULL DEFAULT '',
                parse_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (parse_status IN (
                        'pending',
                        'success',
                        'failed'
                    )),
                parse_error TEXT,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (course_id)
                    REFERENCES courses(id)
                    ON DELETE SET NULL,

                FOREIGN KEY (exam_id)
                    REFERENCES exam_goals(id)
                    ON DELETE SET NULL 
            );
                    
            CREATE INDEX IF NOT EXISTS idx_materials_course_id
                ON materials(course_id);

            CREATE INDEX IF NOT EXISTS idx_materials_exam_id
                ON materials(exam_id);

            CREATE INDEX IF NOT EXISTS idx_materials_parse_status
                ON materials(parse_status);
            """
            """-- 聊天会话表
            CREATE TABLE IF NOT EXISTS chat_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_id INTEGER,
                title TEXT NOT NULL DEFAULT '新对话',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY (exam_id)
                REFERENCES exam_goals(id)
            ON DELETE SET NULL
            );

            -- 聊天消息表
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL
                    CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id)
                REFERENCES chat_conversations(id)
                ON DELETE CASCADE
            );

            -- 提高历史对话和消息查询效率
            CREATE INDEX IF NOT EXISTS idx_chat_conversations_exam_id
                ON chat_conversations(exam_id);

            CREATE INDEX IF NOT EXISTS idx_chat_conversations_updated_at
                ON chat_conversations(updated_at);

            CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_id
                ON chat_messages(conversation_id, id);
                
                
                
            CREATE TABLE IF NOT EXISTS review_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_id INTEGER NOT NULL,
                review_goal TEXT NOT NULL DEFAULT '',
                exam_date TEXT NOT NULL,
                daily_available_minutes INTEGER NOT NULL
                    CHECK (daily_available_minutes > 0),
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'archived', 'stale')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            
                FOREIGN KEY (exam_id)
                    REFERENCES exam_goals(id)
                    ON DELETE CASCADE
            );
            
            CREATE INDEX IF NOT EXISTS idx_review_plans_exam_id
                ON review_plans(exam_id);
            
            CREATE INDEX IF NOT EXISTS idx_review_plans_status
                ON review_plans(status);
            
            
            CREATE TABLE IF NOT EXISTS review_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                day_number INTEGER NOT NULL
                    CHECK (day_number >= 1),
                topic TEXT NOT NULL,
                task_type TEXT NOT NULL
                    CHECK (task_type IN ('learn', 'review', 'practice')),
                priority TEXT NOT NULL
                    CHECK (priority IN ('high', 'medium', 'low')),
                estimated_minutes INTEGER NOT NULL
                    CHECK (estimated_minutes > 0),
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'completed')),
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            
                FOREIGN KEY (plan_id)
                    REFERENCES review_plans(id)
                    ON DELETE CASCADE
            );
            
            CREATE INDEX IF NOT EXISTS idx_review_tasks_plan_id
                ON review_tasks(plan_id);
            
            CREATE INDEX IF NOT EXISTS idx_review_tasks_plan_day
                ON review_tasks(plan_id, day_number, sort_order);

        """

        )

        _migrate_review_plans_status(connection)

    finally:
        connection.close()
