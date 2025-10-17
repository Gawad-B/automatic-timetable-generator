import os
import itertools
import pandas as pd
from collections import defaultdict
import random


def load_csvs(upload_dir):
    # Expect files in upload_dir: courses.csv, instructors.csv, rooms.csv, timeslots.csv, sections.csv
    paths = {
        'courses': f"{upload_dir}/courses.csv",
        'instructors': f"{upload_dir}/instructors.csv",
        'rooms': f"{upload_dir}/rooms.csv",
        'timeslots': f"{upload_dir}/timeslots.csv",
        'sections': f"{upload_dir}/sections.csv",
    }
    dfs = {}
    for k, p in paths.items():
        # First try upload_dir/<k>/<k>.csv (how uploads are stored), then upload_dir/<k>.csv
        alt = os.path.join(upload_dir, k, f"{k}.csv")
        p1 = p
        p2 = alt
        found = None
        for candidate in (p2, p1):
            try:
                dfs[k] = pd.read_csv(candidate)
                found = candidate
                break
            except FileNotFoundError:
                continue
        if found is None:
            raise FileNotFoundError(f"Missing required upload: {k} (tried {p2} and {p1})")
    return dfs['courses'], dfs['instructors'], dfs['rooms'], dfs['timeslots'], dfs['sections']



def parse_qualified_courses(val):
    # instructors.QualifiedCourses may be comma separated
    if pd.isna(val):
        return []
    if isinstance(val, str):
        return [s.strip() for s in val.split(',') if s.strip()]
    if isinstance(val, (list, tuple)):
        return list(val)
    return []



def build_domains(courses_df, instructors_df, rooms_df, timeslots_df, sections_df, force_permissive=False):
    # Required columns checks
    if 'CourseID' not in courses_df.columns:
        raise ValueError('courses.csv must contain CourseID')
    if 'Type' not in courses_df.columns:
        raise ValueError('courses.csv must contain Type')
    if 'InstructorID' not in instructors_df.columns and 'QualifiedCourses' not in instructors_df.columns:
        pass
    if 'RoomID' not in rooms_df.columns:
        raise ValueError('rooms.csv must contain RoomID')
    if 'Type' not in rooms_df.columns:
        raise ValueError('rooms.csv must contain Type (Lab/Lecture)')
    if 'Day' not in timeslots_df.columns or 'StartTime' not in timeslots_df.columns or 'EndTime' not in timeslots_df.columns:
        raise ValueError('timeslots.csv must contain Day, StartTime, EndTime')

    instructors_df = instructors_df.copy()
    if 'QualifiedCourses' in instructors_df.columns:
        instructors_df['_quals'] = instructors_df['QualifiedCourses'].apply(parse_qualified_courses)
    else:
        instructors_df['_quals'] = [[] for _ in range(len(instructors_df))]

    course_types = dict(zip(courses_df['CourseID'], courses_df['Type']))

    if 'SectionID' not in sections_df.columns:
        raise ValueError('sections.csv must include SectionID')

    # Auto-generate sections for all courses if needed
    if len(sections_df) < len(courses_df):
        print(f'[csp] Auto-generating sections for all {len(courses_df)} courses')
        new_sections = []
        for idx, course in courses_df.iterrows():
            course_id = str(course['CourseID'])
            # Generate section ID to match original pattern: level/section format
            # Extract level from course ID (e.g., CSC111 -> 1, CSC221 -> 2, etc.)
            level = 1
            if len(course_id) >= 4 and course_id[-3:].isdigit():
                level_digit = course_id[-3]
                if level_digit.isdigit():
                    level = int(level_digit)
            section_num = (idx % 10) + 1  # Distribute sections 1-10
            section_id = f"{level}/{section_num}"
            
            # Determine required lectures based on course type
            course_type = course.get('Type', 'Lecture')
            if 'Lab' in course_type:
                required_lectures = 2  # Both lecture and lab
            else:
                required_lectures = 1  # Lecture only
            
            new_sections.append({
                'SectionID': section_id,
                'CourseID': course_id,
                'Semester': 'fall',
                'Capacity': 30,
                'RequiredLectures': required_lectures
            })
        sections_df = pd.DataFrame(new_sections)
        print(f'[csp] Generated {len(sections_df)} sections for all courses')

    if 'CourseID' not in sections_df.columns:
        course_ids = list(map(str, courses_df['CourseID'].astype(str)))
        n_sections = len(sections_df)
        n_courses = len(course_ids)
        inferred = None
        if n_courses > 0 and n_sections % n_courses == 0:
            chunk = n_sections // n_courses
            inferred = []
            for i in range(n_sections):
                inferred.append(course_ids[i // chunk])

        if inferred is None or not all(inferred):
            import re
            course_ids_set = set(course_ids)
            inferred = []
            for sid in sections_df['SectionID'].astype(str):
                found = None
                for sep in ('-', '_', ':'):
                    if sep in sid:
                        cand = sid.split(sep, 1)[0]
                        if cand in course_ids_set:
                            found = cand
                            break
                if not found:
                    m = re.match(r'([A-Za-z0-9]+)', sid)
                    if m and m.group(1) in course_ids_set:
                        found = m.group(1)
                inferred.append(found)

        if all(x is not None for x in inferred):
            sections_df = sections_df.copy()
            sections_df['CourseID'] = inferred
        else:
            print('[csp] Warning: could not infer CourseID for some SectionIDs; assigning courses round-robin')
            if len(course_ids) == 0:
                raise ValueError('No courses available to assign to sections')
            sections_df = sections_df.copy()
            n_sections = len(sections_df)
            sections_df['CourseID'] = [course_ids[i % len(course_ids)] for i in range(n_sections)]

    if 'RequiredLectures' not in sections_df.columns:
        sections_df['RequiredLectures'] = 1

    timeslots = []
    for idx, r in timeslots_df.iterrows():
        timeslots.append((r['Day'], r['StartTime'], r['EndTime']))

    rooms = list(rooms_df.to_dict('records'))
    instructors = list(instructors_df.to_dict('records'))

    if len(timeslots) == 0:
        raise ValueError('timeslots.csv contains no rows')
    if len(rooms) == 0:
        raise ValueError('rooms.csv contains no rows')
    if len(instructors) == 0:
        raise ValueError('instructors.csv contains no rows')

    variables = []
    domains = {}
    meta = {}
    rejection_reasons = defaultdict(lambda: defaultdict(int))
    fallbacks_used = defaultdict(list)
    for _, sec in sections_df.iterrows():
        course_id = sec['CourseID']
        section_id = sec['SectionID']
        req = int(sec.get('RequiredLectures', 1))
        ctype = course_types.get(course_id, 'Lecture')
        for i in range(req):
            # Create more descriptive lecture names
            if 'Lab' in ctype and req > 1:
                if i == 0:
                    lecture_name = "Lecture"
                else:
                    lecture_name = "Lab"
            else:
                lecture_name = f"Session{i+1}" if req > 1 else "Lecture"
            
            var = f"{course_id}::{section_id}::{lecture_name}"
            variables.append(var)

            def generate_vals(allow_unqualified=False, allow_room_mismatch=False):
                vals_local = []
                for t in timeslots:
                    for room in rooms:
                        rtype = room.get('Type', 'Lecture')
                        room_mismatch = False
                        if (ctype.lower().startswith('lab') and not rtype.lower().startswith('lab')) or (ctype.lower().startswith('lecture') and rtype.lower().startswith('lab')):
                            room_mismatch = True
                        for instr in instructors:
                            quals = instr.get('_quals', [])
                            instr_unqualified = False
                            if quals and course_id not in quals:
                                instr_unqualified = True
                            
                            # Check instructor day preferences
                            instr_unavailable = False
                            day = t[0]  # timeslot is (day, start, end)
                            pref_slots = instr.get('PreferredSlots', '')
                            if pref_slots and isinstance(pref_slots, str):
                                # Handle "Not on [Day]" preferences
                                if 'Not on' in pref_slots and day in pref_slots:
                                    instr_unavailable = True
                            
                            if instr_unqualified and not allow_unqualified:
                                rejection_reasons[var]['unqualified_instructor'] += 1
                                continue
                            if instr_unavailable and not allow_unqualified:  # treat as similar constraint level
                                rejection_reasons[var]['instructor_unavailable'] += 1
                                continue
                            if room_mismatch and not allow_room_mismatch:
                                rejection_reasons[var]['room_type_mismatch'] += 1
                                continue
                            vals_local.append({'timeslot': t, 'room': room['RoomID'], 'instructor': instr['InstructorID'] if 'InstructorID' in instr else instr.get('Name')})
                return vals_local

            if force_permissive:
                vals = generate_vals(allow_unqualified=True, allow_room_mismatch=True)
                if vals:
                    fallbacks_used[var].append('force_permissive_initial')
            else:
                vals = generate_vals(allow_unqualified=False, allow_room_mismatch=False)
            if not vals:
                vals = generate_vals(allow_unqualified=True, allow_room_mismatch=False)
                if vals:
                    fallbacks_used[var].append('allow_unqualified_instructor')
            if not vals:
                vals = generate_vals(allow_unqualified=False, allow_room_mismatch=True)
                if vals:
                    fallbacks_used[var].append('allow_room_type_mismatch')
            if not vals:
                vals = generate_vals(allow_unqualified=True, allow_room_mismatch=True)
                if vals:
                    fallbacks_used[var].append('allow_unqualified_and_room_mismatch')
            domains[var] = vals
            meta[var] = {'course': course_id, 'section': section_id, 'type': ctype}

    for v in variables:
        meta[v]['rejection_reasons'] = dict(rejection_reasons.get(v, {}))
        meta[v]['fallbacks'] = fallbacks_used.get(v, [])

    return variables, domains, meta



def forward_checking_search(variables, domains, meta):
    assignment = {}

    def consistent(var, val, assignment):
        for v, a in assignment.items():
            if a['timeslot'] == val['timeslot']:
                if a['instructor'] == val['instructor']:
                    return False
                if a['room'] == val['room']:
                    return False
        return True

    local_domains = {v: list(domains[v]) for v in variables}

    def select_unassigned_var(assignment):
        unassigned = [v for v in variables if v not in assignment]
        unassigned.sort(key=lambda x: len(local_domains.get(x, [])))
        return unassigned[0] if unassigned else None

    def backtrack():
        if len(assignment) == len(variables):
            return True
        var = select_unassigned_var(assignment)
        if var is None:
            return True
        # Shuffle domain values to get better day distribution
        domain_vals = list(local_domains.get(var, []))
        random.shuffle(domain_vals)
        
        for val in domain_vals:
            if not consistent(var, val, assignment):
                continue
            assignment[var] = val
            removed = {}
            failure = False
            for other in variables:
                if other in assignment or other == var:
                    continue
                newdom = []
                for oval in local_domains.get(other, []):
                    if oval['timeslot'] == val['timeslot'] and (oval['instructor'] == val['instructor'] or oval['room'] == val['room']):
                        continue
                    newdom.append(oval)
                if len(newdom) == 0:
                    failure = True
                    break
                if len(newdom) < len(local_domains[other]):
                    removed[other] = local_domains[other]
                    local_domains[other] = newdom
            if not failure:
                result = backtrack()
                if result:
                    return True
            for k, v in removed.items():
                local_domains[k] = v
            del assignment[var]
        return False

    success = backtrack()
    if not success:
        return None
    return assignment



# ✅ Fixed Function
def assignments_to_dataframe(assign, meta=None, courses_df=None, instructors_df=None):
    # Map CourseID -> CourseName if available
    course_name_map = {}
    if courses_df is not None and 'CourseID' in courses_df.columns and 'CourseName' in courses_df.columns:
        course_name_map = dict(zip(courses_df['CourseID'].astype(str), courses_df['CourseName']))

    # Map InstructorID -> Name if available
    instructor_name_map = {}
    if instructors_df is not None:
        if 'InstructorID' in instructors_df.columns and 'Name' in instructors_df.columns:
            instructor_name_map = dict(zip(instructors_df['InstructorID'].astype(str), instructors_df['Name']))
        elif 'Name' in instructors_df.columns:
            # If no InstructorID column, use Name as both key and value
            instructor_name_map = dict(zip(instructors_df['Name'].astype(str), instructors_df['Name']))

    rows = []
    for var, val in assign.items():
        course, section, lec = var.split('::')
        day, start, end = val['timeslot']
        course_name = course_name_map.get(course, course)
        instructor_id = val['instructor']
        instructor_name = instructor_name_map.get(str(instructor_id), instructor_id)
        rows.append({
            'CourseID': course,
            'CourseName': course_name,
            'SectionID': section,
            'Session': lec,  # Changed from 'Lecture' to 'Session' to be more accurate
            'Day': day,
            'StartTime': start,
            'EndTime': end,
            'Room': val['room'],
            'Instructor': instructor_name
        })
    return pd.DataFrame(rows)



def generate_timetable_from_uploads(upload_dir):
    courses_df, instructors_df, rooms_df, timeslots_df, sections_df = load_csvs(upload_dir)
    variables, domains, meta = build_domains(courses_df, instructors_df, rooms_df, timeslots_df, sections_df)
    assign = forward_checking_search(variables, domains, meta)
    if assign is None:
        total_vars = len(variables)
        zero_domain = [v for v in variables if not domains.get(v)]
        domain_sizes = sorted([(v, len(domains.get(v, []))) for v in variables], key=lambda x: x[1])
        sample = {}
        for v, sz in domain_sizes[:10]:
            sample[v] = domains.get(v, [])[:5]
        diag_lines = []
        diag_lines.append(f"No valid timetable found. variables={total_vars}, zero_domain_count={len(zero_domain)}")
        if zero_domain:
            diag_lines.append("Variables with empty domain (first 20): " + ", ".join(zero_domain[:20]))
            for v in zero_domain[:10]:
                reasons = meta.get(v, {}).get('rejection_reasons', {})
                if reasons:
                    diag_lines.append(f"  {v} rejection_reasons: " + ", ".join([f"{k}={c}" for k, c in reasons.items()]))
                fb = meta.get(v, {}).get('fallbacks', [])
                if fb:
                    diag_lines.append(f"  {v} fallbacks_used: " + ", ".join(fb))
        diag_lines.append("Smallest domain sizes (var:size): " + ", ".join([f"{v}:{s}" for v, s in domain_sizes[:20]]))
        diag_lines.append("Sample domains (up to 5 values each) for smallest-domain vars:")
        for v, vals in sample.items():
            diag_lines.append(f"  {v} -> {vals}")
        diag_lines.append("Fallbacks used (smallest-domain vars):")
        for v, s in domain_sizes[:10]:
            fb = meta.get(v, {}).get('fallbacks', [])
            if fb:
                diag_lines.append(f"  {v}: " + ", ".join(fb))
        try:
            variables2, domains2, meta2 = build_domains(courses_df, instructors_df, rooms_df, timeslots_df, sections_df, force_permissive=True)
            assign2 = forward_checking_search(variables2, domains2, meta2)
            if assign2 is not None:
                print('[csp] Notice: strict generation failed; permissive generation succeeded')
                return assignments_to_dataframe(assign2, meta=meta2, courses_df=courses_df, instructors_df=instructors_df)
            else:
                diag_lines.append('\nAttempted permissive generation (ignore qualifications and room-type) but it also failed.')
        except Exception as e:
            diag_lines.append(f"\nAttempted permissive generation and it raised an error: {e}")

        diag = "\n".join(diag_lines)
        raise RuntimeError(diag)

    df = assignments_to_dataframe(assign, meta=meta, courses_df=courses_df, instructors_df=instructors_df)
    return df
