import psycopg2
import logging
from datetime import datetime
from enum import Enum
import json
from openai import OpenAI
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# 查询类型枚举
class QueryType(Enum):
    LEARNING_SCHEDULE = "learning_schedule"
    UNIT_TEST = "unit_test"
    EXPERIMENT_REPORT = "experiment_report"
    COURSE_INFO = "course_info"
    STUDENT_PROGRESS = "student_progress"


class AIQueryProcessor:
    def __init__(self, openai_api_key=None, db_config=None, model="gpt-4o", base_url=None):
        """
        初始化 AI 查询处理器
        :param openai_api_key: OpenAI API 密钥（从环境变量或参数获取）
        :param db_config: 数据库配置
        :param model: 大模型名称
        :param base_url: 自定义 API 基础 URL（可选，用于 xiaoai.plus 等第三方服务）
        """
        self.openai_api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY 未设置，请在 .env 文件或环境变量中提供")

        self.db_config = db_config or {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', 'learning_system'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'password')
        }
        self.model = model

        # 配置 OpenAI 客户端，支持自定义 base_url
        self.client = OpenAI(
            api_key=self.openai_api_key,
            base_url=base_url or os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
        )
        logger.info("AIQueryProcessor 初始化完成")

    def process_question(self, question, user_id):
        """
        处理自然语言问题，生成 SQL 并查询数据库
        :param question: 用户的问题
        :param user_id: 学生 ID
        :return: 查询结果
        """
        try:
            # 使用大模型生成 SQL
            query_type, sql, params = self._generate_sql(question, user_id)
            if not sql:
                return {
                    'success': False,
                    'error': '无法生成有效的 SQL 查询',
                    'query_type': None,
                    'result_count': 0
                }

            # 执行查询
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            cursor.execute(sql, params)
            results = cursor.fetchall()
            cursor.close()
            conn.close()

            # 格式化答案
            answer = self._format_answer(query_type, results, question)
            result_count = len(results)

            return {
                'success': True,
                'answer': answer,
                'query_type': query_type.value if query_type else None,
                'sql': sql,
                'results': results,
                'result_count': result_count
            }

        except Exception as e:
            logger.error(f"处理查询失败: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'query_type': None,
                'sql': sql if 'sql' in locals() else None,
                'result_count': 0
            }

    def _generate_sql(self, question, user_id):
        """
        使用大模型生成 SQL 查询
        :param question: 用户的问题
        :param user_id: 学生 ID
        :return: (查询类型, SQL 查询, 参数)
        """
        # 更新后的数据库表结构
        schema = """
        Tables:
        - students (student_id, email, student_name, gender)
        - Intelligent_Supervision (serial_number, course_content, online_learning_date, report_deadline, unit_number, unit_test_date)
        - LabReport (serial_number, student_id, submitted)

        Table relationships:
        - LabReport.serial_number references Intelligent_Supervision.serial_number
        - LabReport.student_id references students.student_id
        """

        # 提示模板
        prompt = f"""
        You are an expert SQL generator. Given a natural language question and a database schema, generate a safe SQL query with parameterized placeholders (%s) and identify the query type. The query should be specific to the user with student_id '{user_id}'.

        Schema:
        {schema}

        Question: {question}

        Output JSON:
        ```json
        {{
            "query_type": "learning_schedule|unit_test|experiment_report|course_info|student_progress",
            "sql": "SELECT ... FROM ... WHERE ...",
            "params": []
        }}
        ```

        Examples:
        Question: "我有哪些作业没交？"
        Output:
        ```json
        {{
            "query_type": "experiment_report",
            "sql": "SELECT lr.serial_number, ins.course_content, ins.report_deadline FROM LabReport lr JOIN Intelligent_Supervision ins ON lr.serial_number = ins.serial_number WHERE lr.student_id = %s AND lr.submitted = FALSE",
            "params": ["{user_id}"]
        }}
        ```

        Question: "什么时候有单元测试？"
        Output:
        ```json
        {{
            "query_type": "unit_test",
            "sql": "SELECT DISTINCT unit_number, unit_test_date FROM Intelligent_Supervision WHERE unit_test_date >= CURRENT_DATE ORDER BY unit_test_date",
            "params": []
        }}
        ```

        Question: "数据库课程有哪些内容？"
        Output:
        ```json
        {{
            "query_type": "course_info",
            "sql": "SELECT serial_number, course_content, online_learning_date, report_deadline FROM Intelligent_Supervision ORDER BY serial_number",
            "params": []
        }}
        ```

        Question: "我的学习进度怎么样？"
        Output:
        ```json
        {{
            "query_type": "student_progress",
            "sql": "SELECT COUNT(*) as total_reports, SUM(CASE WHEN submitted THEN 1 ELSE 0 END) as submitted_reports FROM LabReport WHERE student_id = %s",
            "params": ["{user_id}"]
        }}
        ```

        Ensure the SQL is safe, parameterized, and when applicable, restricted to the user's data (student_id = '{user_id}').
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a SQL generation assistant."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            result = json.loads(response.choices[0].message.content)

            query_type = QueryType(result['query_type']) if result[
                                                                'query_type'] in QueryType.__members__.values() else None
            sql = result['sql']
            params = result['params']

            # 验证 SQL 安全性（简单检查）
            if not sql or 'DROP' in sql.upper() or 'DELETE' in sql.upper() or 'UPDATE' in sql.upper():
                logger.warning("生成 SQL 可能不安全或无效")
                return None, None, None

            return query_type, sql, params

        except Exception as e:
            logger.error(f"生成 SQL 失败: {str(e)}")
            return None, None, None

    def _format_answer(self, query_type, results, question):
        """
        将查询结果格式化为自然语言答案
        :param query_type: 查询类型
        :param results: 查询结果
        :param question: 原始问题
        :return: 格式化答案
        """
        if not results:
            return "没有找到相关记录。"

        if query_type == QueryType.EXPERIMENT_REPORT:
            if len(results[0]) >= 3:  # 包含序号、课程内容、截止日期
                answer = "你的未提交实验报告如下：\n"
                for row in results:
                    serial_number, course_content, deadline = row[:3]
                    answer += f"- 第{serial_number}次：{course_content}，截止日期: {deadline}\n"
                return answer
            else:
                answer = "你的未提交实验报告如下：\n"
                for row in results:
                    answer += f"- 报告序号: {row[0]}\n"
                return answer

        elif query_type == QueryType.UNIT_TEST:
            answer = "单元测试安排如下：\n"
            for row in results:
                if len(row) >= 2:
                    unit_number, test_date = row[:2]
                    answer += f"- 第{unit_number}单元测试，时间: {test_date}\n"
                else:
                    answer += f"- 测试时间: {row[0]}\n"
            return answer

        elif query_type == QueryType.COURSE_INFO:
            answer = "课程内容如下：\n"
            for row in results:
                if len(row) >= 4:
                    serial_number, course_content, learning_date, deadline = row[:4]
                    answer += f"- 第{serial_number}次：{course_content}，学习日期: {learning_date}，报告截止: {deadline}\n"
                else:
                    answer += f"- {row[1] if len(row) > 1 else row[0]}\n"
            return answer

        elif query_type == QueryType.STUDENT_PROGRESS:
            if len(results[0]) >= 2:
                total_reports, submitted_reports = results[0][:2]
                completion_rate = (submitted_reports / total_reports * 100) if total_reports > 0 else 0
                answer = f"你的学习进度：总共{total_reports}个实验报告，已提交{submitted_reports}个，完成率{completion_rate:.1f}%"
                return answer
            else:
                return "你的学习进度数据已查询，具体分析待完善。"

        elif query_type == QueryType.LEARNING_SCHEDULE:
            answer = "学习安排如下：\n"
            for row in results:
                if len(row) >= 3:
                    course_content, learning_date, deadline = row[:3]
                    answer += f"- {course_content}，学习日期: {learning_date}，截止日期: {deadline}\n"
            return answer

        # 默认格式化
        answer = "查询结果：\n"
        for i, row in enumerate(results, 1):
            answer += f"{i}. {' | '.join(str(col) for col in row)}\n"
        return answer

    def get_conversation_suggestions(self, query_type):
        """
        根据查询类型生成建议问题
        :param query_type: 查询类型（QueryType 枚举）
        :return: 建议问题列表
        """
        suggestions = {
            QueryType.LEARNING_SCHEDULE: [
                "这周有什么课程要学？",
                "最近的学习安排是什么？",
                "下个月的课程安排",
                "所有课程的学习时间表"
            ],
            QueryType.UNIT_TEST: [
                "什么时候有单元测试？",
                "第3单元测试是什么时候？",
                "所有单元测试的时间安排",
                "最近的考试安排"
            ],
            QueryType.EXPERIMENT_REPORT: [
                "我有哪些作业没交？",
                "未提交的实验报告有哪些？",
                "本周截止的实验报告",
                "逾期的作业列表"
            ],
            QueryType.COURSE_INFO: [
                "数据库课程有哪些内容？",
                "所有课程的详细信息",
                "课程内容和时间安排",
                "每次课的学习内容"
            ],
            QueryType.STUDENT_PROGRESS: [
                "我的学习进度怎么样？",
                "作业完成情况统计",
                "学习完成度分析",
                "我提交了多少作业？"
            ]
        }
        return suggestions.get(query_type, [])