import psycopg2
import config
import math

# database connection
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=config.DB_HOST,
            database=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASS,
            port=config.DB_PORT
        )
        return conn
    except Exception as e:
        print(f"[ERROR] DB Connection Failed: {e}")
        return None

# execute and commit
def _execute_commit(sql, params):
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            affected = cur.rowcount 
            conn.commit()
            return affected > 0 
    except Exception as e:
        print(f"[ERROR] SQL Action Failed: {e}")
        conn.rollback()
        raise e 
    finally:
        conn.close()

#  Metadata Sync Function 
def mark_as_pending():
    """ ปักธงว่ามีการแก้ไขข้อมูล เพื่อรอ Cron Job มาจัดการตอนเที่ยงคืน """
    sql = f"""
        UPDATE {config.DB_SCHEMA}.system_metadata 
        SET pending_update = TRUE 
        WHERE key = 'bot_sync_status'
    """
    return _execute_commit(sql, None)

# pagination and filtering logic
def get_paginated_list(table_name, order_by_col, page=1, per_page=10, 
                       search_query=None, search_cols=[], 
                       filter_col=None, filter_val=None):
    conn = get_db_connection()
    items = []
    total_pages = 1
    total_count = 0
    
    if conn:
        with conn.cursor() as cur:
            where_clauses = []
            params = []

            if table_name == 'manual_chunks':
                from_sql = f"""
                    {config.DB_SCHEMA}.manual_chunks m
                    LEFT JOIN {config.DB_SCHEMA}.categories c ON m.category_id = c.id
                    LEFT JOIN {config.DB_SCHEMA}.documents d ON m.doc_id = d.id
                    LEFT JOIN {config.DB_SCHEMA}.research_funds f ON m.fund_abbr = f.fund_abbr
                """
                select_sql = """
                    m.*, c.name as category_name, c.main_group, 
                    d.title as doc_title, d.version as doc_version,
                    f.fund_name_th as fund_full_name
                """
            elif table_name in ['support_stories', 'view_support_stories']:
                from_sql = f"""
                    {config.DB_SCHEMA}.support_stories s
                    LEFT JOIN {config.DB_SCHEMA}.categories c ON s.category_id = c.id
                """
                select_sql = "s.*, c.name as category_name"
            else:
                from_sql = f"{config.DB_SCHEMA}.{table_name}"
                select_sql = "*"

            if search_query and search_cols:
                formatted_cols = []
                for col in search_cols:
                    if table_name in ['manual_chunks', 'support_stories', 'view_support_stories']:
                        if col == 'category_name': formatted_cols.append("c.name")
                        elif col == 'main_group': formatted_cols.append("c.main_group")
                        elif col == 'doc_title' and table_name == 'manual_chunks': formatted_cols.append("d.title")
                        elif col == 'fund_full_name' and table_name == 'manual_chunks': formatted_cols.append("f.fund_name_th")
                        else: formatted_cols.append(f"{col}::text")
                    else:
                        formatted_cols.append(f"{col}::text")
                
                search_parts = [f"{col} ILIKE %s" for col in formatted_cols] 
                where_clauses.append("(" + " OR ".join(search_parts) + ")")
                term = f"%{search_query}%"
                params.extend([term] * len(formatted_cols))

            if filter_col and filter_val and filter_val != 'all':
                actual_filter_col = filter_col
                if table_name in ['manual_chunks', 'support_stories', 'view_support_stories']:
                    if filter_col == 'category_name': actual_filter_col = "c.name"
                    elif filter_col == 'main_group': actual_filter_col = "c.main_group"
                    elif filter_col == 'doc_title': actual_filter_col = "d.title"
                    elif filter_col == 'data_type' and table_name == 'manual_chunks': actual_filter_col = "m.data_type"

                where_clauses.append(f"{actual_filter_col} = %s")
                params.append(filter_val)

            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)

            cur.execute(f"SELECT COUNT(*) FROM {from_sql} {where_sql}", tuple(params))
            total_count = cur.fetchone()[0]
            total_pages = max(1, math.ceil(total_count / per_page))
            offset = (page - 1) * per_page
            
            data_query = f"""
                SELECT {select_sql} FROM {from_sql} {where_sql}
                ORDER BY {order_by_col} LIMIT %s OFFSET %s
            """
            cur.execute(data_query, tuple(params + [per_page, offset]))
            
            cols = [desc[0] for desc in cur.description]
            items = [dict(zip(cols, row)) for row in cur.fetchall()]
            
        conn.close()
    return items, total_pages, total_count

# research funds
def create_fund(data):
    sql = f"""INSERT INTO {config.DB_SCHEMA}.research_funds 
    (fund_abbr, fund_name_th, fund_name_en, fiscal_year, source_agency, start_period, end_period, status)
    VALUES (%(fund_abbr)s, %(fund_name_th)s, %(fund_name_en)s, %(fiscal_year)s, %(source_agency)s, %(start_period)s, %(end_period)s, %(status)s)"""
    success = _execute_commit(sql, data)
    if success: mark_as_pending()
    return success

def update_fund(fund_id, data):
    data['pk'] = fund_id
    sql = f"""UPDATE {config.DB_SCHEMA}.research_funds SET 
    fund_abbr=%(fund_abbr)s, fund_name_th=%(fund_name_th)s, fund_name_en=%(fund_name_en)s, fiscal_year=%(fiscal_year)s, 
    source_agency=%(source_agency)s, start_period=%(start_period)s, end_period=%(end_period)s, status=%(status)s WHERE fund_id=%(pk)s"""
    success = _execute_commit(sql, data)
    if success: mark_as_pending()
    return success

def delete_fund(fund_id):
    success = _execute_commit(f"DELETE FROM {config.DB_SCHEMA}.research_funds WHERE fund_id = %s", (fund_id,))
    if success: mark_as_pending()
    return success

# glossary
def create_glossary(data):
    sql = f"INSERT INTO {config.DB_SCHEMA}.glossary_terms (word, meaning, word_type) VALUES (%(word)s, %(meaning)s, %(word_type)s)"
    success = _execute_commit(sql, data)
    if success: mark_as_pending()
    return success

def update_glossary(word_id, data):
    data['pk'] = word_id
    sql = f"UPDATE {config.DB_SCHEMA}.glossary_terms SET word=%(word)s, meaning=%(meaning)s, word_type=%(word_type)s WHERE word_id=%(pk)s"
    success = _execute_commit(sql, data)
    if success: mark_as_pending()
    return success

def delete_glossary(word_id):
    success = _execute_commit(f"DELETE FROM {config.DB_SCHEMA}.glossary_terms WHERE word_id = %s", (word_id,))
    if success: mark_as_pending()
    return success

# manuals
def create_manual_chunk(data):
    sql = f"""INSERT INTO {config.DB_SCHEMA}.manual_chunks (doc_id, category_id, topic, section, step_number, content, data_type, fund_abbr)
    VALUES (%(doc_id)s, %(category_id)s, %(topic)s, %(section)s, %(step_number)s, %(content)s, %(data_type)s, %(fund_abbr)s)"""
    success = _execute_commit(sql, data)
    if success: mark_as_pending()
    return success

def update_manual_chunk(chunk_id, data):
    data['pk'] = chunk_id
    sql = f"""UPDATE {config.DB_SCHEMA}.manual_chunks SET topic=%(topic)s, content=%(content)s, section=%(section)s, step_number=%(step_number)s, 
    fund_abbr=%(fund_abbr)s, data_type=%(data_type)s, doc_id=%(doc_id)s, category_id=%(category_id)s WHERE id=%(pk)s"""
    success = _execute_commit(sql, data)
    if success: mark_as_pending()
    return success

def delete_manual_chunk(chunk_id):
    success = _execute_commit(f"DELETE FROM {config.DB_SCHEMA}.manual_chunks WHERE id = %s", (chunk_id,))
    if success: mark_as_pending()
    return success

# support stories
def create_support_story(data):
    sql = f"INSERT INTO {config.DB_SCHEMA}.support_stories (category_id, scenario, solution) VALUES (%(category_id)s, %(scenario)s, %(solution)s)"
    success = _execute_commit(sql, data)
    if success: mark_as_pending()
    return success

def update_support_story(pk_id, data):
    data['pk'] = pk_id
    sql = f"UPDATE {config.DB_SCHEMA}.support_stories SET scenario=%(scenario)s, solution=%(solution)s, category_id=%(category_id)s WHERE id=%(pk)s"
    success = _execute_commit(sql, data)
    if success: mark_as_pending()
    return success

def delete_support_story(story_id):
    success = _execute_commit(f"DELETE FROM {config.DB_SCHEMA}.support_stories WHERE id = %s", (story_id,))
    if success: mark_as_pending()
    return success

# documents
def create_document(data):
    sql = f"INSERT INTO {config.DB_SCHEMA}.documents (title, version, last_updated) VALUES (%(title)s, %(version)s, %(last_updated)s)"
    success = _execute_commit(sql, data)
    if success: mark_as_pending()
    return success

def update_document(doc_id, data):
    data['pk'] = doc_id
    sql = f"UPDATE {config.DB_SCHEMA}.documents SET title=%(title)s, version=%(version)s, last_updated=%(last_updated)s WHERE id=%(pk)s"
    success = _execute_commit(sql, data)
    if success: mark_as_pending()
    return success

def delete_document(doc_id):
    success = _execute_commit(f"DELETE FROM {config.DB_SCHEMA}.documents WHERE id = %s", (doc_id,))
    if success: mark_as_pending()
    return success

# categories
def create_category(data):
    sql = f"INSERT INTO {config.DB_SCHEMA}.categories (name, main_group, description) VALUES (%(name)s, %(main_group)s, %(description)s)"
    success = _execute_commit(sql, data)
    if success: mark_as_pending()
    return success

def update_category(cat_id, data):
    data['pk'] = cat_id
    sql = f"UPDATE {config.DB_SCHEMA}.categories SET name=%(name)s, main_group=%(main_group)s, description=%(description)s WHERE id=%(pk)s"
    success = _execute_commit(sql, data)
    if success: mark_as_pending()
    return success

def delete_category(cat_id):
    success = _execute_commit(f"DELETE FROM {config.DB_SCHEMA}.categories WHERE id = %s", (cat_id,))
    if success: mark_as_pending()
    return success

# helpers
def get_dropdown_options():
    conn = get_db_connection()
    options = {'categories': [], 'documents': [], 'funds': []}
    if not conn: return options
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT id, name FROM {config.DB_SCHEMA}.categories ORDER BY name ASC")
            options['categories'] = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
            cur.execute(f"SELECT id, title FROM {config.DB_SCHEMA}.documents ORDER BY title ASC")
            options['documents'] = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
            cur.execute(f"SELECT fund_id, fund_abbr, fund_name_th FROM {config.DB_SCHEMA}.research_funds ORDER BY fund_abbr")
            options['funds'] = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
    finally:
        conn.close()
    return options

def get_dashboard_stats():
    conn = get_db_connection()
    stats = {
        'funds_count': 0, 'glossary_count': 0, 'manuals_count': 0,
        'stories_count': 0, 'docs_count': 0, 'cats_count': 0,
        'recent_logs': []
    }
    if not conn: return stats
    try:
        with conn.cursor() as cur:
            tables_to_count = [
                ('funds_count', 'research_funds'),
                ('glossary_count', 'glossary_terms'),
                ('manuals_count', 'manual_chunks'),
                ('stories_count', 'support_stories'),
                ('docs_count', 'documents'),
                ('cats_count', 'categories')
            ]
            for key, table in tables_to_count:
                cur.execute(f"SELECT COUNT(*) FROM {config.DB_SCHEMA}.{table}")
                stats[key] = cur.fetchone()[0]
            try:
                cur.execute(f"SELECT * FROM {config.DB_SCHEMA}.chat_logs ORDER BY created_at DESC")
                cols = [desc[0] for desc in cur.description]
                raw_logs = [dict(zip(cols, row)) for row in cur.fetchall()]
                sessions_dict = {}
                for log in raw_logs:
                    sid = log.get('session_id')
                    if sid not in sessions_dict:
                        sessions_dict[sid] = {
                            'session_id': sid,
                            'last_updated': log['created_at'],
                            'messages': [] 
                        }
                    sessions_dict[sid]['messages'].append(log)
                stats['recent_logs'] = list(sessions_dict.values())[:50]
            except Exception as e:
                stats['recent_logs'] = []
    finally:
        conn.close()
    return stats

def get_distinct_values(table_name, column_name):
    conn = get_db_connection()
    items = []
    if conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT DISTINCT {column_name} FROM {config.DB_SCHEMA}.{table_name} WHERE {column_name} IS NOT NULL AND {column_name} != '' ORDER BY {column_name} ASC")
            items = [row[0] for row in cur.fetchall()]
        conn.close()
    return items

def get_user_by_username(username):
    conn = get_db_connection()
    user = None
    if conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {config.DB_SCHEMA}.users WHERE username = %s", (username,))
            if cur.rowcount > 0:
                user = dict(zip([d[0] for d in cur.description], cur.fetchone()))
        conn.close()
    return user

def get_blocking_ids(child_table, fk_column, parent_id, pk_name='id'):
    conn = get_db_connection()
    results = []
    if conn:
        try:
            with conn.cursor() as cur:
                sql = f"SELECT {pk_name} FROM {config.DB_SCHEMA}.{child_table} WHERE {fk_column} = %s ORDER BY {pk_name} ASC"
                cur.execute(sql, (parent_id,))
                results = [row[0] for row in cur.fetchall()]
        except Exception as e:
            print(f"[DEBUG] get_blocking_ids failed: {e}")
        finally:
            conn.close()
    return results