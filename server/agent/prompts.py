INTENT_SYSTEM_PROMPT = """Classify the user's message into exactly one of these intent labels:
- sleep_start   : user is going to sleep / starting sleep tracking
- sleep_end     : user just woke up / ending sleep tracking
- query_hr      : asking about heart rate
- query_hrv     : asking about HRV
- query_spo2    : asking about SpO2 / oxygen saturation
- health_snapshot : asking for overall health summary / stats / status
- unknown       : anything else

Reply with only the label, nothing else."""
