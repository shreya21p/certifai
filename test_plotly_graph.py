import networkx as nx
import plotly.graph_objects as go
G = nx.DiGraph()
G.add_edge("A", "B")
pos = nx.spring_layout(G)
print(pos)
