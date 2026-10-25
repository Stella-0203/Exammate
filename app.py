
#import streamlit as st

from core.config import DB_PATH
from storage.db import get_connection, init_db


st.set_page_config(
    page_title="ExamMate",
    page_icon="📚",
    layout="wide",
)


@st.cache_resource
def initialize_database():
    """初始化正式数据库；IF NOT EXISTS 不会清空已有数据。"""
    init_db()
    return str(DB_PATH)


def load_dashboard_data():
    """读取课程和考试目标，供首页展示。"""
    with get_connection() as connection:
        courses = connection.execute(
            """
            SELECT id, name
            FROM courses
            ORDER BY id DESC
            """
        ).fetchall()

        exams = connection.execute(
            """
            SELECT
                e.id,
                e.name,
                e.exam_date,
                e.status,
                c.name AS course_name
            FROM exam_goals AS e
            JOIN courses AS c ON c.id = e.course_id
            ORDER BY e.id DESC
            """
        ).fetchall()

        tables = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }

    return courses, exams, tables


st.title("📚 ExamMate")
st.caption("面向考试复习的智能体助手")

try:
    db_path = initialize_database()
    courses, exams, tables = load_dashboard_data()
except Exception as exc:
    st.error("应用初始化失败，请检查数据库配置。")
    st.exception(exc)
    st.stop()

st.success("数据库已连接并完成初始化。")

col1, col2, col3 = st.columns(3)
col1.metric("已有课程", len(courses))
col2.metric("已有考试目标", len(exams))
col3.metric("数据库表", len(tables))

with st.expander("查看数据库信息"):
    st.code(db_path)
    st.write("当前数据库表：")
    st.write(", ".join(sorted(tables)))

st.subheader("我的课程")

if courses:
    st.dataframe(
        [
            {"课程 ID": row["id"], "课程名称": row["name"]}
            for row in courses
        ],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("目前还没有课程。后续将接入课程和考试目标创建功能。")

st.subheader("考试目标")

if exams:
    st.dataframe(
        [
            {
                "考试 ID": row["id"],
                "课程": row["course_name"],
                "考试名称": row["name"],
                "考试日期": row["exam_date"] or "未设置",
                "审核状态": row["status"],
            }
            for row in exams
        ],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("目前还没有考试目标。后续将接入大纲导入、知识点确认和复习计划生成。")
