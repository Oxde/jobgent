from jobgent.pack.factguard import banned_phrases, fact_check, tidy_letter

CORPUS = "Developed trading bots processing over $1M in volume with 150+ users. Python, Docker. HEINEKEN. GitHub Copilot, Claude. 2024 - 2025. Acme posting: Kubernetes, SQL."


def test_numbers_must_exist_in_profile_or_posting():
    r = fact_check("Built bots handling $1M+ for 150 users in 2024", CORPUS)
    assert r.invented_numbers == []
    r = fact_check("Improved speed by 40% for 3000 users", CORPUS)
    assert r.invented_numbers == ["40%", "3000"]


def test_unknown_names_are_marked_not_blocked():
    r = fact_check("Used Kubernetes and Terraform at HEINEKEN with Claude", CORPUS)
    assert r.unverified_names == ["Terraform"]


def test_sentence_starts_and_common_words_are_ignored():
    r = fact_check("The team shipped it. In March I joined. My work used Python.", CORPUS)
    assert r.unverified_names == [] and r.invented_numbers == []


def test_banned_phrases_and_em_dashes():
    letter = "I am writing to express my interest in this role — I am passionate about AI and a team player."
    assert set(banned_phrases(letter)) >= {"i am writing to express my interest", "passionate", "team player"}
    assert "—" not in tidy_letter(letter) and "  " not in tidy_letter(letter)
