# Training Hall and combat balance (November 2026)

## Medieval schools and courses

The Training Hall provides nine distinct schools: Grammar, Rhetoric, Logic (the **trivium**); Arithmetic, Geometry, Astronomy and Music (the **quadrivium**); plus Latin and Commerce & Recordkeeping. The courses draw on medieval liberal-arts teaching and practical literacy, not a literal reconstruction of a particular medieval university.

Every school has eight sequential courses. Courses require **4, 6, 8, 10, 13, 17, 22, and 30 simulated days** respectively (110 simulated days total per school). Work stats improve after course completion, not when enrollment begins. The UI shows durations, work-stat bonuses, active study and progress. The player can enroll in **only one course across all schools** at once; attempting to enroll twice or to skip prerequisites is rejected. A player's study progress is not interrupted by travel or jobs, and simulation time does not run automatically from the wall clock; use ordinary time advances at the tavern (one simulated day per request at most).

The last course earns a one-time, **automatically credited merit**; the record is also visible on the Merits page. Geometry, Astronomy, Music, and Commerce & Recordkeeping also have a modest capstone perk: +2 to a secondary work stat. These modest, permanent effects are easy to balance while a larger education system is still evolving.

## Stamina and combat equipment

- Fighting begins without an entrance fee.
- Guarding costs **2 stamina**.
- Fists cost **2 stamina** per attack.
- Dagger costs **3 stamina** per attack.
- Sword costs **5 stamina**; axe costs **7**, bow **5**.
- Combat spells cost **6 stamina and their existing mana cost**. Melee-enhancing spells also pay their associated physical swing cost.
- Reactive defensive counterattacks are still free. Ordinary guard is an active turn and costs stamina.
- Each equipped weapon/armor item loses **one durability after 12 qualified combat wear events** rather than after each strike. An individual item's counter is stored in the engine state and is independent of other gear. Broken equipment is removed just as before.

### Preservation of previous saves

New duel actions replay under journal ruleset **8**. Earlier rulesets replay using their historical stamina/durability conventions, including ruleset 7's old fist/dagger and guard costs. Existing gold, gear and school-less saves remain compatible. The single-action simulation `WorldEngine.attack()` remains a distinct legacy combat path.

### Future directions

A later iteration can introduce course prerequisites between schools, education fees, certificates and graduations, school-specific job bonuses, and formal course attendance that progresses with real-world elapsed time. These are **not** part of the current implementation.
