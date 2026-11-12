namespace MotionTrace.Core.Athletes;

/// <summary>A selection exists only after at least one confirmed athlete is available.</summary>
public sealed class AthleteSelection
{
    private readonly HashSet<int> available;
    private readonly HashSet<int> selected;

    public AthleteSelection(IEnumerable<int> athleteIds)
    {
        available = athleteIds.ToHashSet();
        if (available.Count == 0) throw new ArgumentException("At least one athlete is required.", nameof(athleteIds));
        selected = new(available);
    }

    public bool Contains(int id) => selected.Contains(id);
    public bool TrySetSelected(int id, bool value)
    {
        if (!available.Contains(id)) throw new ArgumentOutOfRangeException(nameof(id));
        if (!value && selected.Contains(id) && selected.Count == 1) return false;
        if (value) selected.Add(id); else selected.Remove(id);
        return true;
    }

    public void SetAllSelected(bool value)
    {
        if (value) selected.UnionWith(available);
        else
        {
            int retained = selected.Order().First();
            selected.Clear();
            selected.Add(retained);
        }
    }
}
