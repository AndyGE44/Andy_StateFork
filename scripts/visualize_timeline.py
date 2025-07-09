import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.cm as cm


def parse_timeline_file(filepath: str):
    sections = {}
    color_labels = []
    current_section = None

    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                # New section
                current_section = line[1:-1]
                sections[current_section] = []
            elif line.startswith(">"):
                # Parse color label
                cid, cname = line[1:].split(":", 1)
                color_labels.append((int(cid.strip()), cname.strip()))
            else:
                # Parse step data
                try:
                    name, dur, cid = line.rsplit(",", maxsplit=2)
                    sections[current_section].append((name.strip(), float(dur.strip()), int(cid.strip())))
                except ValueError:
                    print(f"Skipping malformed line: {line}")
    return sections, color_labels


def plot_gantt_chart_txt(sections: dict, color_labels: list):
    color_map = cm.get_cmap('tab20', 20)

    fig, ax = plt.subplots(figsize=(12, 0.6 * sum(len(steps) for steps in sections.values())))

    y = 0
    yticks = []
    ylabels = []
    color_legend = {}

    for section, steps in sections.items():
        start_time = 0
        for name, duration, color_id in steps:
            color = color_map(color_id)
            ax.barh(y, duration, left=start_time, height=0.5, color=color, edgecolor='black')
            ax.text(start_time + duration / 2, y, f"{duration:.3f}", ha='center', va='center', fontsize=8, color='black')

            if color_id not in color_legend:
                color_legend[color_id] = color

            yticks.append(y)
            ylabels.append(f"{section}: {name}")
            start_time += duration
            y += 1
        y += 1

    ax.set_xlabel("Time (ms)")
    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels, fontsize=8)
    ax.invert_yaxis()
    ax.set_title("Gantt Timeline of Benchmark Steps")

    handles = [mpatches.Patch(color=color_legend[cid], label=f"{label}") for cid, label in color_labels]
    ax.legend(handles=handles, loc='upper right', bbox_to_anchor=(1.15, 1.05))

    plt.tight_layout()
    plt.savefig("gantt_timeline.png", dpi=300)
    plt.show()

if __name__ == "__main__":
    timeline_file = "timeline_data.txt"
    sect, clabel = parse_timeline_file(timeline_file)
    plot_gantt_chart_txt(sect, clabel)
