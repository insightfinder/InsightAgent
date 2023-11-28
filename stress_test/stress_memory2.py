import psutil
import time

# Define the target memory utilization and the exact duration to reach it
target_memory_percent = 95
increase_duration_seconds = 2700

# Calculate the amount of memory to consume
total_memory = psutil.virtual_memory().total
target_memory = int((target_memory_percent / 100) * total_memory)

# Create a list to store memory allocations
memory_allocations = []

try:
    # Increase memory usage to the target level
    start_time = time.time()
    allocation_size = (target_memory - psutil.virtual_memory().used) // increase_duration_seconds
    count = 0
    while True:
        memory_allocations.append(bytearray(allocation_size))
        count += 1

        # Check if the target memory has been reached
        current_memory = psutil.virtual_memory().used
        percent_memory = psutil.virtual_memory().percent
        print(f"{count}: Current Used Memory: {current_memory} - Memory Used in Percentage: {percent_memory} - Total Memory: {total_memory}")
        if percent_memory >= target_memory_percent:
            break

        # Calculate the elapsed time
        elapsed_time = time.time() - start_time

        # Calculate the remaining time to sleep to reach exactly 2 minutes
        remaining_time = increase_duration_seconds - elapsed_time
        if remaining_time > 0:
            # Sleep for the remaining time divided by the number of remaining allocations
            sleep_interval = remaining_time / (increase_duration_seconds - count)
            time.sleep(sleep_interval)
        else:
            break

    print(f"Reached {target_memory_percent}% memory utilization in {elapsed_time:.2f} seconds.")

except KeyboardInterrupt:
    print("Memory consumption interrupted by user.")

finally:
    # Maintain memory usage for the specified duration
    maintain_duration_seconds = 900  # Adjust this value as needed
    time.sleep(maintain_duration_seconds)

    # Release the allocated memory
    del memory_allocations
    print("Memory released.")
