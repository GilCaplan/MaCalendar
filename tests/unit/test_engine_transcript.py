

def test_spoken_noise_comes_off_in_the_cleanup_stage(sample_config):
    """Gil's architecture call: the person-specific work — vocabulary repair
    and the "mhmm"/"umm" filler — belongs in the INITIAL CLEANUP step, so
    everything downstream is generic. Filler stripping used to live inside
    FastRule's own normalisation, so the DEEP track never got it: real-usage
    review showed the LLM path failing 5 of 5 on rambling dictation opening
    with exactly these words."""
    from assistant.engine.ingest import repair as transcript
    from assistant.engine.state import EngineState

    st = EngineState(raw_text="Alright, we have a movie today from 3pm to 6pm",
                     text="", source="test")
    transcript.run(st, sample_config)
    assert not st.text.lower().startswith("alright")
    assert "movie" in st.text and "3pm" in st.text     # nothing else lost
