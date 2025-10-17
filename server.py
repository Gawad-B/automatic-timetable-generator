import os
import time
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from io import BytesIO
import pandas as pd
import csp
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_BASE = os.path.join(BASE_DIR, 'static', 'uploads')

os.makedirs(UPLOAD_BASE, exist_ok=True)

ALLOWED_TARGETS = {'courses', 'instructors', 'rooms', 'timeslots', 'sections'}



app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/generate', methods=['POST'])
def generate():
    # Generate timetable using uploaded CSVs in static/uploads
    try:
        upload_dir = os.path.join(UPLOAD_BASE)
        df = csp.generate_timetable_from_uploads(upload_dir)
    except Exception as e:
        # Log full traceback to server console for debugging
        traceback.print_exc()
        return jsonify(success=False, message=str(e)), 500

    # Write to Excel in-memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Timetable')
    output.seek(0)

    return (output.read(), 200, {
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'Content-Disposition': 'attachment; filename="timetable.xlsx"'
    })


@app.route('/upload/<target>', methods=['POST'])
def upload(target):
    if target not in ALLOWED_TARGETS:
        return jsonify(success=False, message='Invalid upload target'), 400

    if 'file' not in request.files:
        return jsonify(success=False, message='No file part'), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify(success=False, message='No selected file'), 400

    filename = secure_filename(file.filename)
    # Allow client to request a different saved filename:
    # - send 'save_as' in the form data to force a filename (example: 'courses.csv')
    # - or send 'use_target_name' (true/1) to use '<target><orig_ext>' as the filename
    save_as = request.form.get('save_as')
    use_target_name = request.form.get('use_target_name')

    if save_as:
        # sanitize client-supplied name
        filename = secure_filename(save_as)
    elif use_target_name and use_target_name.lower() in ('1', 'true', 'yes'):
        orig_ext = os.path.splitext(filename)[1]
        filename = secure_filename(f"{target}{orig_ext}")
    # Ensure target directory exists
    target_dir = os.path.join(UPLOAD_BASE, target)
    os.makedirs(target_dir, exist_ok=True)

    save_path = os.path.join(target_dir, filename)
    try:
        # Overwrite existing file if present (user requested behavior)
        file.save(save_path)
        print(f"[upload] saved file for target={target} filename={filename} path={save_path}")
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500

    return jsonify(success=True, message='File uploaded', filename=filename), 200

if __name__ == '__main__':
    app.run(debug=True)