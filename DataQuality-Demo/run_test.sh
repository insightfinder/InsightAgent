python dq-demo-script.py
python convert_logs_to_json.py generated_unique.log -o generated_unique.json
python convert_logs_to_json.py generated_unmatched.log -o generated_unmatched.json
rm -rf generated_unique.log
rm -rf generated_unmatched.log