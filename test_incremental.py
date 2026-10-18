from db import get_checkpoint, get_incremental_jobs


def main():

    print("========== OpsPilot Incremental Monitor ==========")

    # 1. 读取上次扫描水位
    checkpoint = get_checkpoint()

    last_scan_time = checkpoint["LAST_SCAN_TIME"]

    print(f"上次扫描水位: {last_scan_time}")

    # 2. 查询增量JOB
    jobs, scan_upper_bound = get_incremental_jobs(
        last_scan_time
    )

    print(f"本次扫描上界: {scan_upper_bound}")
    print(f"本次查询记录数: {len(jobs)}")

    # 3. 输出增量记录
    for job in jobs:

        print(
            f"[JOB] "
            f"EXECUTION_ID={job['EXECUTION_ID']}, "
            f"NAME={job['JOB_NAME']}, "
            f"STATUS={job['STATUS']}, "
            f"UPDATED_AT={job['UPDATED_AT']}"
        )

    # 注意：
    # 当前只是查询测试，不推进Checkpoint。


if __name__ == "__main__":
    main()