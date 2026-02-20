from flask import Flask, render_template, request, redirect, url_for, flash
import db_actions
import config
import re

# app setup
app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.jinja_env.add_extension('jinja2.ext.do')

# dashboard
@app.route('/')
def index():
    # ดึงตัวเลขสถิติภาพรวมมาขึ้นที่หน้าแรก
    stats = db_actions.get_dashboard_stats()
    return render_template('dashboard.html', stats=stats)

# research funds
@app.route('/funds')
def funds_list():
    # แสดงรายการทุนวิจัย ค้นหาได้ กรองสถานะได้ และแบ่งหน้าได้
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    filter_val = request.args.get('filter', '') 
    status_options = db_actions.get_distinct_values('research_funds', 'status')

    items, total_pages, total_count = db_actions.get_paginated_list(
        table_name='research_funds', 
        order_by_col='fund_id ASC', 
        page=max(1, page),
        search_query=search,
        search_cols=['fund_abbr', 'fund_name_th', 'source_agency'],
        filter_col='status',
        filter_val=filter_val
    )
    return render_template('funds_list.html', funds=items, 
                           page=page, total_pages=total_pages, total_count=total_count,
                           search=search, filter_val=filter_val,
                           status_options=status_options)

@app.route('/funds/add', methods=['GET', 'POST'])
def funds_add():
    # รับข้อมูลจากฟอร์มเพื่อเพิ่มทุนใหม่
    if request.method == 'POST':
        data = request.form.to_dict()
        data.pop('id', None)
        if db_actions.create_fund(data):
            flash('บันทึกสำเร็จ', 'success')
            return redirect(url_for('funds_list'))
        flash('ผิดพลาด: ไม่สามารถเพิ่มข้อมูลได้', 'danger')
    status_options = sorted(list(set(db_actions.get_distinct_values('research_funds', 'status') + ['Y', 'N'])))
    return render_template('funds_form.html', action='add', fund={}, status_options=status_options)

@app.route('/funds/edit/<int:id>', methods=['GET', 'POST'])
def funds_edit(id):
    # ดึงข้อมูลทุนเดิมมาแก้ไขตาม ID
    conn = db_actions.get_db_connection()
    item = {}
    if conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {config.DB_SCHEMA}.research_funds WHERE fund_id=%s", (id,))
            if cur.rowcount > 0:
                item = dict(zip([d[0] for d in cur.description], cur.fetchone()))
        conn.close()
    if request.method == 'POST':
        if db_actions.update_fund(id, request.form.to_dict()):
            flash('แก้ไขสำเร็จ', 'success')
            return redirect(url_for('funds_list'))
        flash('ผิดพลาด', 'danger')
    status_options = sorted(list(set(db_actions.get_distinct_values('research_funds', 'status') + ['Y', 'N'])))
    return render_template('funds_form.html', action='edit', fund=item, status_options=status_options)

@app.route('/funds/delete/<int:id>', methods=['POST'])
def funds_delete(id):
    # ระบบลบทุน: มีการเช็คความสัมพันธ์ว่ามีคู่มือตัวไหนใช้อยู่ไหม ถ้ามีจะบอก ID ทันที
    fund_abbr = None
    conn = db_actions.get_db_connection()
    if conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT fund_abbr FROM {config.DB_SCHEMA}.research_funds WHERE fund_id=%s", (id,))
            res = cur.fetchone()
            if res: fund_abbr = res[0]
        conn.close()

    try:
        if db_actions.delete_fund(id):
            flash(f'ลบทุนวิจัย ID {id} สำเร็จ', 'success')
        else:
            flash(f'ไม่พบข้อมูลทุน ID {id}', 'warning')
    except Exception as e:
        err_msg = str(e).lower()
        if 'manual_chunks' in err_msg:
            # ค้นหา ID คู่มือที่ติดปัญหาอยู่
            ids = db_actions.get_blocking_ids('manual_chunks', 'fund_abbr', fund_abbr)
            id_str = ", ".join(map(str, ids))
            flash(f'ลบไม่สำเร็จ: พบการใช้งานในหน้า "manuals" ID ที่ {id_str} กรุณาลบ หรือ แก้ไข ข้อมูลเหล่านี้ก่อนทำรายการนี้ ', 'danger')
        else:
            flash(f'ลบไม่สำเร็จ: ข้อมูล ID {id} ติดปัญหาอื่น ({e})', 'danger')
    return redirect(url_for('funds_list'))

# glossary
@app.route('/glossary')
def glossary_list():
    # แสดงรายการพจนานุกรมคำศัพท์
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    filter_val = request.args.get('filter', '') 
    type_options = db_actions.get_distinct_values('glossary_terms', 'word_type')

    items, total_pages, total_count = db_actions.get_paginated_list(
        table_name='glossary_terms', 
        order_by_col='word_id ASC', 
        page=max(1, page),
        search_query=search,
        search_cols=['word', 'meaning'], 
        filter_col='word_type',
        filter_val=filter_val
    )
    return render_template('glossary_list.html', terms=items, 
                           page=page, total_pages=total_pages, total_count=total_count,
                           search=search, filter_val=filter_val,
                           type_options=type_options)

@app.route('/glossary/add', methods=['GET', 'POST'])
def glossary_add():
    # เพิ่มคำศัพท์ใหม่
    if request.method == 'POST':
        data = request.form.to_dict()
        data.pop('id', None)
        if db_actions.create_glossary(data):
            flash('เพิ่มสำเร็จ', 'success')
            return redirect(url_for('glossary_list'))
        flash('ผิดพลาด', 'danger')
    type_options = db_actions.get_distinct_values('glossary_terms', 'word_type')
    return render_template('glossary_form.html', action='add', term={}, type_options=type_options)

@app.route('/glossary/edit/<int:id>', methods=['GET', 'POST'])
def glossary_edit(id):
    # แก้ไขคำศัพท์หรือความหมาย
    conn = db_actions.get_db_connection()
    item = {}
    if conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {config.DB_SCHEMA}.glossary_terms WHERE word_id=%s", (id,))
            if cur.rowcount > 0:
                item = dict(zip([d[0] for d in cur.description], cur.fetchone()))
        conn.close()
    if request.method == 'POST':
        if db_actions.update_glossary(id, request.form.to_dict()):
            flash('แก้ไขสำเร็จ', 'success')
            return redirect(url_for('glossary_list'))
        flash('ผิดพลาด', 'danger')
    type_options = db_actions.get_distinct_values('glossary_terms', 'word_type')
    return render_template('glossary_form.html', action='edit', term=item, type_options=type_options)

@app.route('/glossary/delete/<int:id>', methods=['POST'])
def glossary_delete(id):
    # ลบคำศัพท์
    try:
        if db_actions.delete_glossary(id): flash('ลบคำศัพท์สำเร็จ', 'success')
        else: flash('ไม่พบข้อมูล', 'warning')
    except Exception as e: flash(f'ลบไม่สำเร็จ: {e}', 'danger')
    return redirect(url_for('glossary_list'))

# documents
@app.route('/documents')
def documents_list():
    # แสดงรายการเอกสารต้นฉบับ
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    filter_val = request.args.get('filter', '') 
    version_options = db_actions.get_distinct_values('documents', 'version')

    items, total_pages, total_count = db_actions.get_paginated_list(
        table_name='documents', 
        order_by_col='id ASC', 
        page=max(1, page),
        search_query=search,
        search_cols=['title', 'version'],
        filter_col='version',  
        filter_val=filter_val
    )
    return render_template('documents_list.html', docs=items, 
                           page=page, total_pages=total_pages, total_count=total_count,
                           search=search, filter_val=filter_val,
                           version_options=version_options)

@app.route('/documents/add', methods=['GET', 'POST'])
def documents_add():
    # บันทึกข้อมูลเอกสารใหม่
    if request.method == 'POST':
        data = request.form.to_dict()
        data.pop('id', None)
        if db_actions.create_document(data):
            flash('เพิ่มสำเร็จ', 'success')
            return redirect(url_for('documents_list'))
        flash('ผิดพลาด', 'danger')
    return render_template('documents_form.html', action='add', doc={})

@app.route('/documents/edit/<int:id>', methods=['GET', 'POST'])
def documents_edit(id):
    # แก้ไขชื่อเอกสารหรือเวอร์ชัน
    conn = db_actions.get_db_connection()
    item = {}
    if conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {config.DB_SCHEMA}.documents WHERE id=%s", (id,))
            if cur.rowcount > 0:
                item = dict(zip([d[0] for d in cur.description], cur.fetchone()))
        conn.close()
    if request.method == 'POST':
        if db_actions.update_document(id, request.form.to_dict()):
            flash('แก้ไขสำเร็จ', 'success')
            return redirect(url_for('documents_list'))
        flash('ผิดพลาด', 'danger')
    return render_template('documents_form.html', action='edit', doc=item)

@app.route('/documents/delete/<int:id>', methods=['POST'])
def documents_delete(id):
    # ลบเอกสาร: เช็คก่อนว่าติด Manual ตัวไหนอยู่ไหม
    try:
        if db_actions.delete_document(id):
            flash(f'ลบเอกสาร ID {id} สำเร็จ', 'success')
        else:
            flash(f'ไม่พบเอกสาร ID {id}', 'warning')
    except Exception as e:
        err_msg = str(e).lower()
        if 'manual_chunks' in err_msg:
            # ดึง ID ของคู่มือที่ใช้อยู่มาโชว์
            ids = db_actions.get_blocking_ids('manual_chunks', 'doc_id', id)
            id_str = ", ".join(map(str, ids))
            flash(f'ลบไม่สำเร็จ: พบการใช้งานในหน้า "manuals" ID ที่ {id_str} กรุณาลบ หรือ แก้ไข ข้อมูลเหล่านี้ก่อนทำรายการนี้ ', 'danger')
        else:
            flash(f'ลบไม่สำเร็จ: ข้อมูล ID {id} ติดปัญหา ({e})', 'danger')
    return redirect(url_for('documents_list'))

# categories
@app.route('/categories')
def categories_list():
    # รายการหมวดหมู่ข้อมูล
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    filter_val = request.args.get('filter', '') 
    group_options = db_actions.get_distinct_values('categories', 'main_group')

    items, total_pages, total_count = db_actions.get_paginated_list(
        table_name='categories', 
        order_by_col='id ASC', 
        page=max(1, page),
        search_query=search,
        search_cols=['name', 'description', 'main_group'],
        filter_col='main_group',
        filter_val=filter_val
    )
    return render_template('categories_list.html', cats=items, 
                           page=page, total_pages=total_pages, total_count=total_count,
                           search=search, filter_val=filter_val,
                           group_options=group_options)

@app.route('/categories/add', methods=['GET', 'POST'])
def categories_add():
    # เพิ่มหมวดหมู่ใหม่
    if request.method == 'POST':
        data = request.form.to_dict()
        data.pop('id', None)
        if db_actions.create_category(data):
            flash('เพิ่มสำเร็จ', 'success')
            return redirect(url_for('categories_list'))
        flash('ผิดพลาด', 'danger')
    group_options = db_actions.get_distinct_values('categories', 'main_group')
    return render_template('categories_form.html', action='add', cat={}, group_options=group_options)

@app.route('/categories/edit/<int:id>', methods=['GET', 'POST'])
def categories_edit(id):
    # แก้ไขหมวดหมู่
    conn = db_actions.get_db_connection()
    item = {}
    if conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {config.DB_SCHEMA}.categories WHERE id=%s", (id,))
            if cur.rowcount > 0:
                item = dict(zip([d[0] for d in cur.description], cur.fetchone()))
        conn.close()
    if request.method == 'POST':
        if db_actions.update_category(id, request.form.to_dict()):
            flash('แก้ไขสำเร็จ', 'success')
            return redirect(url_for('categories_list'))
        flash('ผิดพลาด', 'danger')
    group_options = db_actions.get_distinct_values('categories', 'main_group')
    return render_template('categories_form.html', action='edit', cat=item, group_options=group_options)

@app.route('/categories/delete/<int:id>', methods=['POST'])
def categories_delete(id):
    # ลบหมวดหมู่: เช็คทั้งใน "คู่มือ" และ "เคสช่วยเหลือ" ถ้ามีคนใช้งานอยู่จะแจ้งเตือนพร้อมบอก ID ทันที
    try:
        if db_actions.delete_category(id):
            flash(f'ลบหมวดหมู่ ID {id} สำเร็จ', 'success')
        else:
            flash(f'ไม่พบหมวดหมู่ ID {id}', 'warning')
    except Exception as e:
        err_msg = str(e).lower()
        if 'manual_chunks' in err_msg:
            ids = db_actions.get_blocking_ids('manual_chunks', 'category_id', id)
            id_str = ", ".join(map(str, ids))
            flash(f'ลบไม่สำเร็จ: พบการใช้งานในหน้า "manuals" ID ที่ {id_str} กรุณาลบ หรือ แก้ไข ข้อมูลเหล่านี้ก่อนทำรายการนี้ ', 'danger')
        elif 'support_stories' in err_msg:
            ids = db_actions.get_blocking_ids('support_stories', 'category_id', id)
            id_str = ", ".join(map(str, ids))
            flash(f'ลบไม่สำเร็จ: พบการใช้งานในหน้า "stories" ID ที่ {id_str} กรุณาลบ หรือ แก้ไข ข้อมูลเหล่านี้ก่อนทำรายการนี้ ', 'danger')
        else:
            flash(f'ลบไม่สำเร็จ: ข้อมูล ID {id} ติดปัญหาความสัมพันธ์อื่น', 'danger')
    return redirect(url_for('categories_list'))

# manuals
@app.route('/manuals')
def manuals_list():
    # รายการเนื้อหาย่อยของคู่มือสำหรับสอนบอท
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    filter_val = request.args.get('filter', '') 
    type_options = db_actions.get_distinct_values('manual_chunks', 'data_type')

    items, total_pages, total_count = db_actions.get_paginated_list(
        table_name='manual_chunks',  
        order_by_col='id ASC', 
        page=max(1, page),
        search_query=search,
        search_cols=['topic', 'content', 'category_name', 'doc_title'],
        filter_col='data_type', 
        filter_val=filter_val
    )
    return render_template('manuals_list.html', chunks=items, 
                           page=page, total_pages=total_pages, total_count=total_count,
                           search=search, filter_val=filter_val,
                           type_options=type_options) 

@app.route('/manuals/add', methods=['GET', 'POST'])
def manuals_add():
    # เพิ่มคู่มือใหม่ (มีการจัดการเรื่องชื่อย่อทุนเป็นค่าว่างให้เป็น NULL)
    if request.method == 'POST':
        data = request.form.to_dict()
        data.pop('id', None)
        
        if not data.get('fund_abbr') or data.get('fund_abbr').strip() == "":
            data['fund_abbr'] = None
            
        if db_actions.create_manual_chunk(data):
            flash('เพิ่มสำเร็จ', 'success')
            return redirect(url_for('manuals_list'))
        flash('ผิดพลาด', 'danger')
    options = db_actions.get_dropdown_options()
    db_types = db_actions.get_distinct_values('manual_chunks', 'data_type')
    data_type_options = sorted(list(set(db_types + ['manual', 'guide', 'warning', 'info', 'troubleshoot', 'contact', 'rule'])))
    return render_template('manuals_form.html', action='add', chunk={}, categories=options['categories'], documents=options['documents'], funds=options['funds'], data_type_options=data_type_options)

@app.route('/manuals/edit/<int:id>', methods=['GET', 'POST'])
def manuals_edit(id):
    # แก้ไขคู่มือตาม ID
    conn = db_actions.get_db_connection()
    item = {}
    if conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {config.DB_SCHEMA}.manual_chunks WHERE id=%s", (id,))
            if cur.rowcount > 0:
                item = dict(zip([d[0] for d in cur.description], cur.fetchone()))
        conn.close()
    if request.method == 'POST':
        data = request.form.to_dict()
        
        if not data.get('fund_abbr') or data.get('fund_abbr').strip() == "":
            data['fund_abbr'] = None
            
        if db_actions.update_manual_chunk(id, data): 
            flash('แก้ไขสำเร็จ', 'success')
            return redirect(url_for('manuals_list'))
        flash('ผิดพลาด', 'danger')
        
    options = db_actions.get_dropdown_options()
    db_types = db_actions.get_distinct_values('manual_chunks', 'data_type')
    data_type_options = sorted(list(set(db_types + ['manual', 'guide', 'warning', 'info', 'troubleshoot', 'contact', 'rule'])))
    
    return render_template('manuals_form.html', action='edit', chunk=item, categories=options['categories'], documents=options['documents'], funds=options['funds'], data_type_options=data_type_options)

@app.route('/manuals/delete/<int:id>', methods=['POST'])
def manuals_delete(id):
    # ลบคู่มือออกจากระบบ
    try:
        if db_actions.delete_manual_chunk(id): flash('ลบเนื้อหาสำเร็จ', 'success')
        else: flash('ไม่พบข้อมูล', 'warning')
    except Exception as e: flash(f'ลบไม่สำเร็จ: {e}', 'danger')
    return redirect(url_for('manuals_list'))

# support stories
@app.route('/stories')
def stories_list():
    # รายการเคสช่วยเหลือและวิธีแก้ไขสำหรับสอนบอท
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    filter_val = request.args.get('filter', '') 
    options = db_actions.get_dropdown_options()

    items, total_pages, total_count = db_actions.get_paginated_list(
        table_name='support_stories', 
        order_by_col='id ASC', 
        page=max(1, page),
        search_query=search,
        search_cols=['scenario', 'solution', 'category_name'],
        filter_col='category_name',
        filter_val=filter_val
    )
    return render_template('stories_list.html', stories=items, 
                           page=page, total_pages=total_pages, total_count=total_count,
                           search=search, filter_val=filter_val,
                           categories=options['categories'])

@app.route('/stories/add', methods=['GET', 'POST'])
def stories_add():
    # เพิ่มเคสใหม่
    if request.method == 'POST':
        data = request.form.to_dict()
        data.pop('id', None) 
        if db_actions.create_support_story(data):
            flash('เพิ่มสำเร็จ', 'success')
            return redirect(url_for('stories_list'))
        flash('ผิดพลาด', 'danger')
    options = db_actions.get_dropdown_options()
    return render_template('stories_form.html', action='add', story={}, categories=options['categories'])

@app.route('/stories/edit/<int:id>', methods=['GET', 'POST'])
def stories_edit(id):
    # แก้ไขเคสเดิม
    conn = db_actions.get_db_connection()
    item = {}
    if conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT ss.*, c.name as category_name FROM {config.DB_SCHEMA}.support_stories ss LEFT JOIN {config.DB_SCHEMA}.categories c ON ss.category_id=c.id WHERE ss.id=%s", (id,))
            if cur.rowcount > 0:
                item = dict(zip([d[0] for d in cur.description], cur.fetchone()))
        conn.close()
    if request.method == 'POST':
        if db_actions.update_support_story(id, request.form.to_dict()):
            flash('แก้ไขสำเร็จ', 'success')
            return redirect(url_for('stories_list'))
        flash('ผิดพลาด', 'danger')
    options = db_actions.get_dropdown_options()
    return render_template('stories_form.html', action='edit', story=item, categories=options['categories'])

@app.route('/stories/delete/<int:id>', methods=['POST'])
def stories_delete(id):
    # ลบเคสช่วยเหลือ
    try:
        if db_actions.delete_support_story(id): flash('ลบเคสสำเร็จ', 'success')
        else: flash('ไม่พบข้อมูล', 'warning')
    except Exception as e: flash(f'ลบไม่สำเร็จ {e}', 'danger')
    return redirect(url_for('stories_list'))

# run app
if __name__ == '__main__':
    app.run(debug=True, port=5000)