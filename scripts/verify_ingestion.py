"""
End-to-End verification script for ObserveAI trace ingestion pipeline.
Seeds Postgres, sends test events via API Gateway, and queries ClickHouse to verify.
Does not require any host-level dependencies other than docker compose.
"""

import hashlib
import json
import time
import urllib.request
import urllib.error
import subprocess

def run_cmd(args):
    """Run a terminal command and return output."""
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running {' '.join(args)}:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
        return None
    return result.stdout.strip()

def main():
    print("====================================================")
    print("       ObserveAI Pipeline Verification Script       ")
    print("====================================================\n")
    
    # 1. Test data setup config
    tenant_id = "11111111-1111-1111-1111-111111111111"
    project_id = "22222222-2222-2222-2222-222222222222"
    api_key_id = "33333333-3333-3333-3333-333333333333"
    raw_key = "obs_testkey123456"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    
    print("1. Seeding test tenant, project, and API key into Postgres...")
    
    # Clean up previous test seed if any
    cleanup_sql = f"""
    DELETE FROM api_keys WHERE id = '{api_key_id}';
    DELETE FROM projects WHERE id = '{project_id}';
    DELETE FROM tenants WHERE id = '{tenant_id}';
    """
    run_cmd(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "observeai", "-d", "observeai", "-c", cleanup_sql])

    # Insert test data
    insert_sql = f"""
    INSERT INTO tenants (id, name, email, plan) VALUES ('{tenant_id}', 'Test Tenant', 'test@example.com', 'free');
    INSERT INTO projects (id, tenant_id, name) VALUES ('{project_id}', '{tenant_id}', 'Test Project');
    INSERT INTO api_keys (id, tenant_id, project_id, key_hash, key_prefix, name) VALUES ('{api_key_id}', '{tenant_id}', '{project_id}', '{key_hash}', 'obs_', 'Test Key');
    """
    result = run_cmd(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "observeai", "-d", "observeai", "-c", insert_sql])
    if result is None:
        print("❌ Failed to seed database. Is PostgreSQL running?")
        return
    print("✅ Postgres seeded successfully.\n")
    
    # 2. Send traces to API Gateway
    gateway_url = "http://localhost:3000/v1/traces"
    headers = {
        "Authorization": f"Bearer {raw_key}",
        "Content-Type": "application/json"
    }
    
    print("2. Sending 10 test traces to Go API Gateway...")
    success_count = 0
    for i in range(1, 11):
        payload = {
            "model": f"model-test-{'A' if i % 2 == 0 else 'B'}",
            "prompt": f"Test prompt number {i}",
            "response": f"Test response number {i}",
            "input_tokens": 10 * i,
            "output_tokens": 5 * i,
            "latency_ms": 100 + i * 10,
            "status": "success",
            "session_id": "44444444-4444-4444-4444-444444444444"
        }
        
        req = urllib.request.Request(
            gateway_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 202:
                    resp_data = json.loads(response.read().decode("utf-8"))
                    print(f"  → Trace {i} accepted. ID: {resp_data.get('trace_id')}")
                    success_count += 1
                else:
                    print(f"  → Trace {i} failed with status: {response.status}")
        except urllib.error.URLError as e:
            print(f"  → Trace {i} error connecting to API Gateway: {e}")
            
    print(f"\nResult: Sent {success_count}/10 traces successfully.\n")
    if success_count == 0:
        print("❌ Aborting: No traces were accepted by the API Gateway.")
        return

    # 3. Wait for Kafka consumer to process and ClickHouse to flush
    print("3. Waiting 5 seconds for stream consumer batch flush...")
    time.sleep(5)
    
    # 4. Check ClickHouse traces table
    print("4. Querying ClickHouse for traces...")
    ch_query = "SELECT count(), model FROM observeai.traces WHERE tenant_id = '11111111-1111-1111-1111-111111111111' GROUP BY model"
    ch_result = run_cmd(["docker", "compose", "exec", "-T", "clickhouse", "clickhouse-client", "--query", ch_query])
    
    print("\nClickHouse Ingestion Summary:")
    print("--------------------------------------------------")
    if ch_result:
        print(ch_result)
        # Sum trace counts from result lines
        total_ingested = 0
        for line in ch_result.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                total_ingested += int(parts[0])
        print("--------------------------------------------------")
        print(f"Total Ingested Traces in ClickHouse: {total_ingested}")
        if total_ingested == success_count:
            print("\n🎉 SUCCESS: All sent traces are successfully stored in ClickHouse!")
        else:
            print(f"\n⚠️ WARNING: Sent {success_count} traces, but ClickHouse contains {total_ingested}.")
    else:
        print("No traces found in ClickHouse.")
        print("\n❌ FAILURE: Traces did not arrive in ClickHouse.")

if __name__ == "__main__":
    main()
