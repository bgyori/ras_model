import sys
import collections
import re
import itertools
import operator
import lxml.etree
import pygraphviz

Species = collections.namedtuple('Species',
                                 'id name label compartment')

class Reaction(collections.namedtuple(
        'ReactionBase',
        'id name label reactants products kf kr')):
    def __repr__(self):
        simple_attrs = ('id', 'name', 'label')
        simple_attr_repr = ', '.join('{0}={1!r}'.format(a, getattr(self, a))
                                     for a in simple_attrs)
        species_repr = ', '.join(
            ['{0}=({1})'.format(et, ', '.join(s.name for s in getattr(self, et)))
             for et in 'reactants', 'products'])
        param_repr = ', '.join(['{0}={1!r}'.format(pt, getattr(self, pt))
                                for pt in 'kf', 'kr'])
        return '{0}({1}, {2}, {3})'.format(type(self).__name__,
                                           simple_attr_repr, species_repr,
                                           param_repr)

def xpath(obj, path, single=True):
    result = map(unicode, obj.xpath(path, namespaces={'s': ns}))
    if single:
        if len(result) == 0:
            result = None
        elif len(result) == 1:
            result = result[0]
        else:
            raise ValueError("XPath expression matches more than one value")
    return result

def reactionSpecies(element, entity_type):
    entity_type = entity_type.title()
    query = 's:listOf{}s/s:speciesReference/@species'.format(entity_type)
    return xpath(element, query, single=False)

def species_by_label(pattern, multi=False):
    if isinstance(pattern, basestring):
        pattern = r'^{}$'.format(re.escape(pattern))
    gen = (s for s in species if re.search(pattern, s.label))
    return list(gen) if multi else next(gen)

def neighbor_set(nodes):
    return set(itertools.chain.from_iterable(graph.neighbors(n) for n in nodes))

def reverse_reaction(reaction, keep_appearance=False):
    for s in reaction.reactants:
        if s.id in graph:
            reverse_edge(s.id, reaction.id, keep_appearance)
    for s in reaction.products:
        if s.id in graph:
            reverse_edge(reaction.id, s.id, keep_appearance)

def reverse_edge(u, v, keep_appearance):
    e = graph.get_edge(u, v)
    attrs = dict(e.attr)
    if keep_appearance:
        attrs['dir'] = 'back'
    graph.add_edge(v, u, **attrs)
    graph.remove_edge(u, v)

cluster_seq = itertools.count()
def add_box(*species_list):
    nodes = [s.id for s in species_list]
    name = 'cluster_{}'.format(next(cluster_seq))
    cluster = graph.add_subgraph(nodes, name, color='none', bgcolor='gray94')
    return cluster

# All the dark ("4") colors from the graphviz color set.
color_cycle = itertools.cycle((
        'antiquewhite4', 'aquamarine4', 'azure4', 'bisque4', 'blue4', 'brown4',
        'burlywood4', 'cadetblue4', 'chartreuse4', 'chocolate4', 'coral4',
        'cornsilk4', 'cyan4', 'darkgoldenrod4', 'darkolivegreen4',
        'darkorange4', 'darkorchid4', 'darkseagreen4', 'deeppink4',
        'deepskyblue4', 'dodgerblue4', 'firebrick4', 'gold4', 'goldenrod4',
        'green4', 'honeydew4', 'hotpink4', 'indianred4', 'ivory4', 'khaki4',
        'lavenderblush4', 'lemonchiffon4', 'magenta4', 'maroon4',
        'mediumorchid4', 'mediumpurple4', 'mistyrose4', 'navajowhite4',
        'olivedrab4', 'orange4', 'orangered4', 'orchid4', 'peachpuff4', 'pink4',
        'plum4', 'purple4', 'red4', 'rosybrown4', 'royalblue4', 'salmon4',
        'seagreen4', 'seashell4', 'sienna4', 'skyblue4', 'slateblue4', 'snow4',
        'springgreen4', 'steelblue4', 'tan4', 'thistle4', 'tomato4',
        'turquoise4', 'violetred4', 'wheat4', 'yellow4'))

#####
# Parse SBML file.

ns = 'http://www.sbml.org/sbml/level2'
qnames = dict((tag, lxml.etree.QName(ns, tag).text)
              for tag in ('species', 'reaction'))

sbml_file = open(sys.argv[1])

species = []
reactions = []
species_id_map = {}
for event, element in lxml.etree.iterparse(sbml_file, tag=qnames['species']):
    species_id = element.get('id')
    name = element.get('name')
    label = xpath(element, 's:notes/text()').strip()
    # special fixup for weird ATP label
    if label == 'ATP  1.2e9':
        label = 'ATP'
    compartment = xpath(element, 's:annotation/text()')
    if compartment is not None:
        compartment = compartment.strip().lower()
        if 'endo' in compartment:
            label = 'endo|' + label
    s = Species(species_id, name, label, compartment)
    species.append(s)
    species_id_map[s.id] = s
    if s.name in globals():
        raise RuntimeError('duplicate component name: {}'.format(s.name))
    globals()[s.name] = s
sbml_file.seek(0)
for event, element in lxml.etree.iterparse(sbml_file, tag=qnames['reaction']):
    rxn_id = element.get('id')
    label = re.sub(r' +', ' ', element.get('name'))
    name, label = label.split(' ', 1)
    label, kf, kr = label.rsplit(' ', 2)
    reactants = tuple(map(species_id_map.get, reactionSpecies(element, 'reactant')))
    products = tuple(map(species_id_map.get, reactionSpecies(element, 'product')))
    r = Reaction(rxn_id, name, label, reactants, products, kf, kr)
    reactions.append(r)
    if r.name in globals():
        raise RuntimeError('duplicate component name: {}'.format(r.name))
    globals()[r.name] = r

#####
# Construct graphviz representation of reaction network.

graph = pygraphviz.AGraph(directed=True, rankdir='LR', compound=True)
graph.node_attr.update(fontname='Helvetica')
graph.edge_attr.update(arrowsize=0.7)
for s in species:
    label = '<{0.label} <sup>{0.name}</sup>>'.format(s)
    graph.add_node(s.id, _type='species', label=label, shape='none',
                   bgcolor='white', margin=0.01, height=0)
for r in reactions:
    graph.add_node(r.id, _type='reaction', label=r.name, shape='none',
                   fontcolor='#13ac4a', width=0, height=0, margin=0.05)
    color = next(color_cycle)
    for reactant in r.reactants:
        graph.add_edge(reactant.id, r.id, color=color)
    for product in r.products:
        graph.add_edge(r.id, product.id, color=color)

# delete some "nuisance" nodes from the graph
for label in 'ATP', 'Inh':
    graph.remove_node(species_by_label(label).id)

# Fix reactions that were specified "backwards" in the original model. This
# swaps the direction of all edges on these reaction nodes.
for r in (v804, v807, v812, v813, v822, v823, v824, v825,
          v808, v811, v809, v826, v810, v827):
    reverse_reaction(r)
# Fix "retrograde" reactions -- those whose forward direction is logically
# "backward" in the signaling network. This switches the logical edge direction
# without changing the visual appearance (i.e. which end has the arrowhead),
# leading to improved graph layout.
for r in v443,:
    reverse_reaction(r, keep_appearance=True)

## Plasma membrane receptors and ligands

# single ErbB1
add_box(c531)
# single receptors
add_box(c2, c141, c140, c143)
# 2:3 / 2:4 dimers
add_box(c288, c117)
# ligands
add_box(c1, c514)
# ligand-bound single receptors
add_box(c3, c142, c144)
# ligand-bound receptor dimers
add_box(c4, c145, c146, c147, c355, c345, c516, c517)
# ATP-and-ligand-bound receptor dimers
add_box(c116, c122, c127, c128, c168, c139, c137, c138)
# Phosphorylated dimers (dimer#P)
add_box(c5, c148, c149, c150, c335, c336, c289)
# Phosphorylated monomers
add_box(c330, c87, c331, c332)

## Adapters

# GAP
add_box(c14)
# dimer#P:GAP
add_box(c341, c344, c291, c15, c151, c152, c153)
# Shc
add_box(c31)
# Grb2
add_box(c22)
# Sos
add_box(c24)
# Shc#P
add_box(c40)
# (Shc#P):Grb2
add_box(c39)
# (Shc#P):Grb2:Sos
add_box(c38)
# Grb2:SOS
add_box(c30)
# dimer#P:GAP:Shc
add_box(c347, c348, c294, c171, c172, c173, c32)
# dimer#P:GAP:(Shc#P)
add_box(c351, c354, c297, c180, c181, c182, c33)
# dimer#P:GAP:(Shc#P):Grb2
add_box(c357, c360, c300, c189, c190, c191, c34)
# dimer#P:GAP:(Shc#P):Grb2:Sos
add_box(c363, c366, c303, c198, c199, c200, c35)
# dimer#P:GAP:Grb2
add_box(c381, c384, c312, c225, c226, c227, c23)
# dimer:P:GAP:Grb2:Sos
add_box(c387, c390, c315, c234, c235, c236, c25)

## Endosome receptors and ligands

# single receptors
add_box(c156, c154, c155, c6)
# 2:2 / 2:3 / 2:4 dimers
add_box(c425, c339, c340)
# ligands
add_box(c16, c515)
# degraded EGF
add_box(c13)
# ligand-bound single receptors
add_box(c10, c157, c158)
# ligand-bound receptor dimers
add_box(c11, c159, c160, c161, c421, c422, c518, c519)
# degraded receptor pool
add_box(c86)
# ATP-and-ligand-bound receptor dimers
add_box(c126, c123, c124, c125, c169, c170)
# Phosphorylated dimers (dimer#P)
add_box(c8, c162, c163, c164, c337, c338, c290)

## RTK phosphatase

# RTK Phosphatase
add_box(c280)
# dimer#P:Phosphatase
add_box(c415, c416, c281, c283, c282, c417, c418)


# Delete stuff we haven't explicitly enumerated through add_box calls above.
box_nodes = [n for g in graph.subgraphs() for n in g.nodes()]
nodes_keep = set(box_nodes).union(neighbor_set(box_nodes))
nodes_drop = set(graph.nodes()) - nodes_keep
dropped_species_nodes = set(n for n in nodes_drop if n.attr['_type'] == 'species')
drop2 = neighbor_set(dropped_species_nodes)
for n in list(nodes_drop.union(drop2)):
    graph.remove_node(n)

# Collapse sets of parallel reaction nodes.
node_to_subgraph = {n: g for g in graph.subgraphs() for n in g.nodes()}
rxn_nodes = [n for n in graph.nodes() if n.attr['_type'] == 'reaction']
rxn_cluster_neighbors = [
    tuple(sorted(node_to_subgraph[sn] for sn in graph.neighbors(rn)))
    for rn in rxn_nodes]
rxn_to_cn = dict(zip(rxn_nodes, rxn_cluster_neighbors))
# Sort reaction nodes based on which species subgraphs (clusters) they are
# adjacent to. Map subgraphs to their ids because graph equality in pygraphviz
# is VERY expensive -- it serializes them to strings and compares those!
rxn_nodes.sort(key=lambda r: map(id, rxn_to_cn[r]))
for subgraphs, node_iter in itertools.groupby(rxn_nodes, rxn_to_cn.get):
    nodes = list(node_iter)
    if (all(sum(n.attr['_type'] == 'species' for n in sg) in (1, len(nodes)) for sg in subgraphs) and
        len(nodes) > 1):
        node_id = 'reaction_' + '_'.join(sg.name for sg in subgraphs)
        label = r'\n'.join(sorted(n.attr['label'] for n in nodes))
        graph.add_node(node_id, label=label, fontcolor='#13ac4a', shape='box',
                       width=0, height=0, margin=0.05, color='#13ac4a20')
        r_nodes = graph.predecessors(nodes[0])
        p_nodes = graph.successors(nodes[0])
        base_edge_attrs = {'color': next(color_cycle)}
        for ntype, species_nodes in ('reactant', r_nodes), ('product', p_nodes):
            for species_node in species_nodes:
                sg = node_to_subgraph[species_node]
                u, v = sg.nodes_iter().next(), node_id
                if ntype == 'reactant':
                    lheadtail = 'ltail'
                else:
                    lheadtail = 'lhead'
                    u, v = v, u
                attrs = dict(base_edge_attrs)
                if len(sg) > 1:
                    attrs.update({lheadtail: sg.name}, arrowsize=1.4,
                                 style='bold')
                graph.add_edge(u, v, **attrs)
        for n in nodes:
            graph.remove_node(n)

# TEST
#graph.add_subgraph([s.id for s in species if s.id in graph and 'endo' in s.compartment],
#                   'endosome', color='red')

# TEMP
# for sg in graph.subgraphs():
#     sg.graph_attr['label'] = sg.name
#     globals()[sg.name] = sg

graph.write('chen_2009.dot')

#####
# Debugging/cleanup checks

# determine truly redundant species -- same name, same compartment
sa = sorted(species, key=lambda s: (s.label, s.compartment))
rs = [x
      for x in ((n, map(lambda s: s.compartment, it))
          for n, it in itertools.groupby(sa, lambda s: s.label))
      if len(x[1]) == 2 and x[1][0] == x[1][1]]

# find reactions where product is not a trivial concatenation of reactants
# (e.g. A + B -> A:B)
mismatch_rxns = [r for r in reactions
                 if r.products[0].label != ':'.join([s.label for s in r.reactants])]
