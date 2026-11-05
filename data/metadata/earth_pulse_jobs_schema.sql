CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            region_id TEXT NOT NULL,
            parameters TEXT NOT NULL,
            status TEXT NOT NULL,
            progress_pct REAL DEFAULT 0.0,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            error_summary TEXT,
            output_references TEXT,
            provenance_links TEXT
        );
CREATE TABLE analysis_runs (
            run_id TEXT PRIMARY KEY,
            analysis_type TEXT NOT NULL,
            region_id TEXT NOT NULL,
            status TEXT NOT NULL,
            executed_at TEXT NOT NULL,
            completed_at TEXT,
            parameters TEXT,
            outputs TEXT,
            metadata TEXT
        );
