from hello_support.cases import CASES, cites_only_known_sections, citations, evaluate
from hello_support.postprocess import looks_french, normalize_citations, simulation_footer

STOPPED = {"tool": "get_service_status", "ok": True, "arguments": {"service_name": "postgres"},
           "result": {"service": "postgres", "status": "stopped", "simulated": True, "scenario": "stopped"}}


def test_citations_are_normalized_to_known_ids():
    text, unknown = normalize_citations("See [postgres_connection.md#Service_status] and redis_unreachable.md#Checks, "
                                        "and kafka.md#Lag")
    assert "postgres_connection.md#Service status" in text and "_status" not in text
    assert "redis_unreachable.md#Checks" in text
    assert unknown == ["kafka.md#Lag"]


def test_footer_states_simulation_and_no_action():
    footer = simulation_footer([STOPPED], "Mon application ne parvient plus à se connecter")
    assert "simulation" in footer and "postgres = stopped" in footer and "Aucune action" in footer
    assert "No corrective action" in simulation_footer([], "My website is down")


def test_language_heuristic():
    assert looks_french("Combien d'incidents postgres ces 30 derniers jours ?")
    assert not looks_french("My website shows 502 Bad Gateway")


def test_case_checks_on_a_good_and_a_bad_c1_state():
    c1 = next(c for c in CASES if c.id == "C1")
    good = {"route": {"intent": "malfunction", "service": "postgres"}, "observations": [STOPPED],
            "answer": "Observation : le service PostgreSQL est arrêté (statut simulé). Vérifiez les logs de la base "
                      "avant de le relancer. Sources : postgres_connection.md#Service status"}
    assert all(evaluate(c1, good).values())
    bad = {**good, "observations": [], "answer": "It is probably running. Sources: postgres_connection.md#Service_status"}
    result = evaluate(c1, bad)
    assert not result["statut observé = stopped"] and not result["citations exactes"] and not result["en français"]


def test_citation_check_rejects_invented_sections():
    assert citations("x postgres_connection.md#Checks, y") == ["postgres_connection.md#Checks"]
    assert not cites_only_known_sections({"answer": "Source: kafka_lag.md#Consumers"})


def test_status_assertion_ignores_conditionals():
    from hello_support.cases import asserts_status
    assert not asserts_status({"answer": "Si le serveur Redis est arrêté, les connexions sont refusées."})
    assert asserts_status({"answer": "Observation : le service est arrêté."})
