# University and free-choice courses (November 2026)

The former Training Hall is now the **University**, with a compact **five-column by two-row grid** of ten expandable school cards (responsive on smaller screens).

The active schools are: Rhetoric, Logic, Arithmetic, Astronomy, Music, Latin, Commerce, Writing & Recordkeeping, Physical Training and Weapons Training.

Grammar and Geometry are retired from **new** enrollments, but their existing course records and merits remain in the save-replay model. The former Commerce & Recordkeeping school retains the `commerce` identifier, now shown as Commerce; the independent `writing` school starts fresh.

Each active school offers eight courses of durations **4, 6, 8, 10, 13, 17, 22 and 30 simulated days**, respectively. You can **choose any course in any order**, provided it is not already completed and you are not studying another course. Tuition is **8, 12, 16, 20, 25, 30, 40 and 50 gold**, respectively, paid to the crown when enrollment starts. These are fixed by course tier and displayed before payment. A completed course cannot be purchased twice; replay and request-id deduplication prevent duplicate charges.

Course completion grants its designated work-stat bonus. The school grants **one merit automatically** when all eight distinct courses have been completed, regardless of their order. Selected schools additionally award small work-stat capstone bonuses. A graduation benefit is one-time and paid in full only on the eighth distinct completion.

The University page intentionally does not duplicate work-stat information found on the Home page. The small active-course summary reports remaining **simulated** time, not elapsed real time. Courses currently progress only with advancing game time, and only one may be active at a time.

The old `enroll_course` action remains supported for historical journal replay; all new user enrollments use `enroll_course_choice`, ruleset 9. Old Grammar and Geometry enrollment actions replay faithfully without granting users new enrollments in those retired schools. No already-earned legacy merit is removed.
