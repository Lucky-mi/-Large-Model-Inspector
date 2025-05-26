from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import logging
from datetime import datetime
import traceback
import psycopg2
from enhanced_ai_processor import AIQueryProcessor, QueryType  # 修正导入，确保与 enhanced_ai_processor.py 一致

app = Flask(__name__)
CORS(app)  # Allow cross-domain requests

# Configure logging with file output for better debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backend.log'),  # Save logs to a file
        logging.StreamHandler()  # Also print logs to console
    ]
)
logger = logging.getLogger(__name__)

# Global configuration
class Config:
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    DATABASE_CONFIG = {
        'host': os.getenv('DB_HOST', '110.41.115.206'),
        'port': int(os.getenv('DB_PORT', 8000)),
        'database': os.getenv('DB_NAME', 'finance01'),
        'user': os.getenv('DB_USER', 'python01_user51'),
        'password': os.getenv('DB_PASSWORD', 'python01_user51@123')
    }
    MODEL_NAME = os.getenv('MODEL_NAME', 'gpt-4o')  # Align with enhanced_ai_processor.py

# Validate environment variables
def validate_config():
    """Validate required environment variables and database connectivity"""
    errors = []
    if not Config.OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY is not set in environment variables")

    # Validate database configuration
    required_db_keys = ['host', 'port', 'database', 'user', 'password']
    for key in required_db_keys:
        if not Config.DATABASE_CONFIG.get(key):
            errors.append(f"Database config missing: {key}")

    if errors:
        return False, errors

    # Test database connection
    try:
        conn = psycopg2.connect(**Config.DATABASE_CONFIG)
        conn.close()
        logger.info("Database connection successful")
        return True, None
    except Exception as e:
        errors.append(f"Database connection failed: {str(e)}")
        return False, errors

# Initialize AIQueryProcessor with detailed error handling
ai_processor = None
try:
    is_valid, config_errors = validate_config()
    if not is_valid:
        logger.error("Configuration validation failed: %s", "; ".join(config_errors))
        raise ValueError("Invalid configuration: " + "; ".join(config_errors))

    ai_processor = AIQueryProcessor(
        openai_api_key=Config.OPENAI_API_KEY,
        db_config=Config.DATABASE_CONFIG,
        model=Config.MODEL_NAME
    )
    logger.info("AIQueryProcessor initialized successfully")
except Exception as e:
    logger.error(f"AIQueryProcessor initialization failed: {str(e)}\n{traceback.format_exc()}")
    ai_processor = None

# Validate user ID
def validate_user(user_id):
    """Validate if the user exists in the database"""
    try:
        conn = psycopg2.connect(**Config.DATABASE_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT student_id FROM students WHERE student_id = %s", (user_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result is not None
    except Exception as e:
        logger.error(f"User validation failed: {str(e)}")
        return False

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    db_status = "connected"
    try:
        conn = psycopg2.connect(**Config.DATABASE_CONFIG)
        conn.close()
    except Exception as e:
        db_status = f"disconnected: {str(e)}"

    return jsonify({
        'status': 'healthy' if ai_processor else 'unhealthy',
        'timestamp': datetime.now().isoformat(),
        'ai_processor_ready': ai_processor is not None,
        'database_status': db_status
    })

@app.route('/api/login', methods=['POST'])
def login():
    """Login validation (simplified, checks student ID existence)"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        if not user_id:
            return jsonify({
                'success': False,
                'error': '学生ID不能为空',
                'error_code': 'EMPTY_INPUT'
            }), 400

        if not validate_user(user_id):
            return jsonify({
                'success': False,
                'error': '学生ID不存在',
                'error_code': 'INVALID_CREDENTIALS'
            }), 400

        logger.info(f"用户登录成功: {user_id}")
        return jsonify({
            'success': True,
            'message': '登录成功'
        })
    except Exception as e:
        logger.error(f"登录失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'登录失败: {str(e)}',
            'error_code': 'LOGIN_ERROR'
        }), 500

@app.route('/api/query', methods=['POST'])
def process_query():
    """
    处理自然语言查询
    请求格式:
    {
        "question": "我有哪些作业没交？",
        "user_id": "202311081040",
        "include_sql": true,
        "include_raw_results": false
    }
    """
    try:
        if not ai_processor:
            return jsonify({
                'success': False,
                'error': 'AI查询服务暂时不可用。请检查服务器日志以获取详细信息。',
                'error_code': 'SERVICE_UNAVAILABLE'
            }), 503

        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': '请求数据格式错误',
                'error_code': 'INVALID_REQUEST'
            }), 400

        question = data.get('question', '').strip()
        user_id = data.get('user_id')

        if not question:
            return jsonify({
                'success': False,
                'error': '问题不能为空',
                'error_code': 'EMPTY_QUESTION'
            }), 400

        if not user_id or not validate_user(user_id):
            return jsonify({
                'success': False,
                'error': '无效的学生ID',
                'error_code': 'INVALID_USER_ID'
            }), 400

        logger.info(f"处理查询: {question} (用户: {user_id})")

        result = ai_processor.process_question(question, user_id)

        response = {
            'success': result['success'],
            'timestamp': datetime.now().isoformat(),
            'question': question
        }

        if result['success']:
            response.update({
                'answer': result['answer'],
                'query_type': result['query_type'],
                'result_count': result['result_count']
            })

            if data.get('include_sql', True):
                response['sql'] = result['sql']

            if data.get('include_raw_results', False):
                response['raw_results'] = result['results']

            if result['query_type']:
                try:
                    query_type_enum = QueryType(result['query_type'])
                    suggestions = ai_processor.get_conversation_suggestions(query_type_enum)
                    response['suggestions'] = suggestions
                except:
                    pass

            logger.info(f"查询成功: {result['result_count']}条结果")
            return jsonify(response)
        else:
            response.update({
                'error': result['error'],
                'error_code': 'QUERY_FAILED'
            })

            if data.get('include_sql', True) and 'sql' in result:
                response['sql'] = result['sql']

            logger.warning(f"查询失败: {result['error']}")
            return jsonify(response), 400

    except Exception as e:
        logger.error(f"处理查询时发生错误: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': '服务器内部错误',
            'error_code': 'INTERNAL_ERROR',
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/suggestions', methods=['GET'])
def get_suggestions():
    """获取查询建议"""
    try:
        suggestions = {
            'learning_schedule': [
                "这周有什么课程要学？",
                "最近的学习安排是什么？",
                "下个月的课程安排",
                "所有课程的学习时间表"
            ],
            'unit_test': [
                "什么时候有单元测试？",
                "第3单元测试是什么时候？",
                "所有单元测试的时间安排",
                "最近的考试安排"
            ],
            'experiment_report': [
                "我有哪些作业没交？",
                "未提交的实验报告有哪些？",
                "本周截止的实验报告",
                "逾期的作业列表"
            ],
            'course_info': [
                "数据库课程有哪些内容？",
                "所有课程的详细信息",
                "课程内容和时间安排",
                "每次课的学习内容"
            ],
            'student_progress': [
                "我的学习进度怎么样？",
                "作业完成情况统计",
                "学习完成度分析",
                "我提交了多少作业？"
            ]
        }

        return jsonify({
            'success': True,
            'suggestions': suggestions,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"获取建议时发生错误: {str(e)}")
        return jsonify({
            'success': False,
            'error': '获取建议失败',
            'error_code': 'SUGGESTIONS_ERROR'
        }), 500
@app.route('/api/change_password', methods=['POST'])
def change_password():
    """Change user password"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        old_password = data.get('old_password')
        new_password = data.get('new_password')

        if not user_id or not old_password or not new_password:
            return jsonify({
                'success': False,
                'error': '学生ID、旧密码和新密码不能为空',
                'error_code': 'EMPTY_INPUT'
            }), 400

        # 验证用户和旧密码
        conn = psycopg2.connect(**Config.DATABASE_CONFIG)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT student_id FROM students WHERE student_id = %s AND password = %s",
            (user_id, old_password)
        )
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'error': '旧密码错误或学生ID不存在',
                'error_code': 'INVALID_CREDENTIALS'
            }), 400

        # 更新密码
        cursor.execute(
            "UPDATE students SET password = %s WHERE student_id = %s",
            (new_password, user_id)
        )
        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"密码修改成功: {user_id}")
        return jsonify({
            'success': True,
            'message': '密码修改成功'
        })

    except Exception as e:
        logger.error(f"密码修改失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'密码修改失败: {str(e)}',
            'error_code': 'CHANGE_PASSWORD_ERROR'
        }), 500
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
