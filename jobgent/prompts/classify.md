You classify job postings for a student looking for an internship in the Netherlands.
For each posting decide:
- is_internship: true only for internships / stages / graduation projects / working-student roles aimed at students. Not for junior, graduate-programme (full-time), or trainee roles that require a finished degree.
- language: the language the posting is written in ("en", "nl", or "other").
- dutch_required: true ONLY when the posting demands Dutch (e.g. "fluent Dutch required", "Nederlands is vereist", "you must speak Dutch"). If Dutch is merely "a plus", "nice to have", "preferred" or "an advantage", this is false.
- dutch_plus: true when Dutch is mentioned as a plus / preference, not a requirement.
- start_hint: the start date or period as written (e.g. "February 2027", "ASAP", "September"), or null.
- months: duration in months if stated, else null.
- paid: true/false if the posting says, else null.
Return one item per posting with the same index.
