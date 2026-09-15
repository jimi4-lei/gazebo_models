#!/usr/bin/env python3
"""Convert a COLLADA (.dae) file to Wavefront OBJ (+ MTL), stdlib only."""
import sys, xml.etree.ElementTree as ET
import re

NS = {'c': 'http://www.collada.org/2005/11/COLLADASchema'}

def parse_sources(geom):
    srcs = {}
    for src in geom.findall('.//c:source', NS):
        fa = src.find('c:float_array', NS)
        if fa is None:
            continue
        vals = [float(x) for x in fa.text.split()]
        acc = src.find('c:technique_common/c:accessor', NS)
        stride = int(acc.get('stride', 3)) if acc is not None else 3
        srcs['#' + src.get('id')] = (vals, stride)
    return srcs

def read_inputs(geom):
    inputs = {}
    for inp in geom.findall('.//c:input', NS):
        inputs[inp.get('semantic')] = inp.get('source')
    return inputs

def strip_ns(tag):
    return tag.split('}')[-1]

def main(dae_path, obj_path, mtl_path):
    tree = ET.parse(dae_path)
    root = tree.getroot()

    # materials: effect id -> diffuse rgba
    effects = {}
    for mat in root.findall('.//c:library_materials/c:material', NS):
        ie = mat.find('c:instance_effect', NS)
        if ie is not None:
            effects[mat.get('id')] = ie.get('url')

    diffuses = {}
    for eff in root.findall('.//c:library_effects/c:effect', NS):
        c = eff.find('.//c:lambert/c:diffuse/c:color', NS)
        if c is None:
            c = eff.find('.//c:phong/c:diffuse/c:color', NS)
        if c is not None:
            diffuses['#' + eff.get('id')] = [float(x) for x in c.text.split()]

    # geometries
    geoms = {}
    lib_geoms = root.find('c:library_geometries', NS)
    if lib_geoms is not None:
        for g in lib_geoms.findall('c:geometry', NS):
            mesh = g.find('c:mesh', NS)
            if mesh is None:
                continue
            srcs = parse_sources(mesh)
            positions = []
            pos_src = None
            for vsrc in mesh.findall('c:vertices', NS):
                for inp in vsrc.findall('c:input', NS):
                    if inp.get('semantic') == 'POSITION':
                        pos_src = inp.get('source')
            if pos_src and pos_src in srcs:
                vals, stride = srcs[pos_src]
                positions = [tuple(vals[i:i+3]) for i in range(0, len(vals), stride)]
            # per-material triangles
            tris = {}  # mat symbol -> list of (vi, ti, ni)
            for tri in mesh.findall('c:triangles', NS):
                mat = tri.get('material', 'default')
                offs = {}
                for inp in tri.findall('c:input', NS):
                    offs[inp.get('semantic')] = (int(inp.get('offset')), inp.get('source'))
                voff = offs.get('VERTEX', (0, None))[0]
                toff = offs.get('TEXCOORD')
                noff = offs.get('NORMAL')
                plist = [int(x) for x in tri.find('c:p', NS).text.split()]
                # COLLADA offsets are tuple positions and are not guaranteed to
                # be dense (or unique across semantics).
                npt = max(offset for offset, _ in offs.values()) + 1
                lst = tris.setdefault(mat, [])
                for i in range(0, len(plist), npt):
                    p = plist[i:i+npt]
                    lst.append((p[voff],
                                p[toff[0]] if toff else 0,
                                p[noff[0]] if noff else 0))
            for pl in mesh.findall('c:polylist', NS):
                mat = pl.get('material', 'default')
                offs = {}
                for inp in pl.findall('c:input', NS):
                    offs[inp.get('semantic')] = (int(inp.get('offset')), inp.get('source'))
                voff = offs.get('VERTEX', (0, None))[0]
                toff = offs.get('TEXCOORD')
                noff = offs.get('NORMAL')
                plist = [int(x) for x in pl.find('c:p', NS).text.split()]
                vcount = [int(x) for x in pl.find('c:vcount', NS).text.split()]
                npt = max(offset for offset, _ in offs.values()) + 1
                lst = tris.setdefault(mat, [])
                idx = 0
                for cnt in vcount:
                    poly = []
                    for _ in range(cnt):
                        p = plist[idx:idx+npt]; idx += npt
                        poly.append((p[voff],
                                     p[toff[0]] if toff else 0,
                                     p[noff[0]] if noff else 0))
                    for k in range(1, cnt-1):
                        lst.append(poly[0]); lst.append(poly[k]); lst.append(poly[k+1])
            geoms['#' + g.get('id')] = (positions, tris, mesh)

    # scene: walk nodes, apply transforms
    out_v = []   # list of (pos, rgb)
    out_vt = []
    out_vn = []
    out_f = []  # list of (matname, [(v,vt,vn)...])
    cur_mat = ['default']

    def mat_rgb(matname):
        if matname == 'default':
            return (0.8, 0.8, 0.8)
        return tuple(float(x) for x in matname.split('_')[1:4])

    def mat_of(instance_mat):
        if instance_mat is None:
            return 'default'
        target = instance_mat.get('target')
        mid = target.lstrip('#')
        eff = effects.get(mid)
        rgba = diffuses.get(eff, [0.8, 0.8, 0.8, 1]) if eff else None
        if rgba is None:
            return 'default'
        return 'mat_%.2f_%.2f_%.2f' % tuple(rgba[:3])

    def compose(m, t):
        # 4x4 matrix multiply
        return [[sum(m[i][k]*t[k][j] for k in range(4)) for j in range(4)] for i in range(4)]

    def apply(m, p):
        return [sum(m[i][k]*p[k] for k in range(3)) + m[i][3] for i in range(3)]

    def parse_matrix(txt):
        v = [float(x) for x in txt.split()]
        return [v[0:4], v[4:8], v[8:12], v[12:16]]

    def identity():
        return [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]

    def walk(node, M):
        for child in node:
            tag = strip_ns(child.tag)
            if tag == 'node':
                M2 = M
                for e in child:
                    et = strip_ns(e.tag)
                    if et == 'matrix':
                        M2 = compose(parse_matrix(e.text), M2)
                    elif et == 'translate':
                        t = [float(x) for x in e.text.split()]
                        T = identity()
                        T[0][3], T[1][3], T[2][3] = t
                        M2 = compose(T, M2)
                    elif et == 'scale':
                        s = [float(x) for x in e.text.split()]
                        S = identity()
                        S[0][0], S[1][1], S[2][2] = s
                        M2 = compose(S, M2)
                    elif et == 'rotate':
                        ax = e.text.split()
                        axis = [float(ax[0]), float(ax[1]), float(ax[2])]
                        ang = float(ax[3])
                        import math
                        n = math.sqrt(sum(a*a for a in axis)) or 1.0
                        axis = [a/n for a in axis]
                        c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
                        x, y, z = axis
                        R = [[c+x*x*(1-c), x*y*(1-c)-z*s, x*z*(1-c)+y*s],
                             [y*x*(1-c)+z*s, c+y*y*(1-c), y*z*(1-c)-x*s],
                             [z*x*(1-c)-y*s, z*y*(1-c)+x*s, c+z*z*(1-c)]]
                        T = identity()
                        T[:3] = [R[i]+[0] for i in range(3)]
                        M2 = compose(T, M2)
                # instance_geometry
                for e in child:
                    if strip_ns(e.tag) == 'instance_geometry':
                        url = e.get('url')
                        if url in geoms:
                            positions, tris, meshel = geoms[url]
                            srcs = parse_sources(meshel)
                            # bind_material
                            symbol2mat = {}
                            bm = e.find('.//c:bind_material', NS)
                            if bm is not None:
                                for tm in bm.findall('.//c:technique_common/c:instance_material', NS):
                                    symbol2mat[tm.get('symbol')] = mat_of(tm)
                            # texcoords/normals sources
                            tsrc = nsrc = None
                            for tri_or_pl in list(meshel.findall('c:triangles', NS)) + list(meshel.findall('c:polylist', NS)):
                                for inp in tri_or_pl.findall('c:input', NS):
                                    if inp.get('semantic') == 'TEXCOORD':
                                        tsrc = inp.get('source')
                                    if inp.get('semantic') == 'NORMAL':
                                        nsrc = inp.get('source')
                            texcoords = []
                            if tsrc and tsrc in srcs:
                                vals, stride = srcs[tsrc]
                                texcoords = [tuple(vals[i:i+2]) for i in range(0, len(vals), stride)]
                            normals = []
                            if nsrc and nsrc in srcs:
                                vals, stride = srcs[nsrc]
                                normals = [tuple(vals[i:i+3]) for i in range(0, len(vals), stride)]

                            for symbol, flist in tris.items():
                                matname = symbol2mat.get(symbol, 'default')
                                rgb = mat_rgb(matname)
                                base_v = len(out_v)
                                for p in positions:
                                    q = apply(M, p)
                                    out_v.append((q, rgb))
                                base_t = len(out_vt)
                                out_vt.extend(texcoords)
                                base_n = len(out_vn)
                                # transform normals by rotation part (inverse-transpose approx: use R directly for rigid)
                                R = [row[:3] for row in M[:3]]
                                for nn in normals:
                                    out_vn.append([sum(R[i][k]*nn[k] for k in range(3)) for i in range(3)])
                                # ``flist`` is a flat triangle-vertex stream.
                                # Keep each group of three vertices as one OBJ
                                # face; writing each vertex as its own ``f``
                                # record creates invalid one-vertex faces.
                                faces = []
                                for i in range(0, len(flist), 3):
                                    triangle = []
                                    for vi, ti, ni in flist[i:i + 3]:
                                        triangle.append((
                                            vi + 1 + base_v,
                                            ti + 1 + base_t if texcoords else 0,
                                            ni + 1 + base_n if normals else 0,
                                        ))
                                    if len(triangle) == 3:
                                        faces.append(triangle)
                                out_f.append((matname, faces))
                walk(child, M2)
            elif tag == 'instance_node':
                url = child.get('url')
                nid = url.lstrip('#')
                for target in root.iter('{http://www.collada.org/2005/11/COLLADASchema}node'):
                    if target.get('id') == nid:
                        walk(target, M)
                        break

    scene = root.find('.//c:library_visual_scenes/c:visual_scene', NS)
    walk(scene, identity())

    # dedupe materials
    mats = {}
    for name, _ in out_f:
        if name != 'default':
            r, g, b = [float(x) for x in name.split('_')[1:4]]
            mats[name] = (r, g, b)

    with open(obj_path, 'w') as f:
        f.write('# Converted from COLLADA\nmtllib %s\n' % mtl_path.split('/')[-1])
        for v, rgb in out_v:
            # 带顶点色 — MuJoCo 支持 OBJ 顶点色渲染（MTL 材质不支持）
            f.write('v %f %f %f %f %f %f\n' % (v[0], v[1], v[2], rgb[0], rgb[1], rgb[2]))
        for t in out_vt:
            f.write('vt %f %f\n' % (t[0], t[1]))
        for n in out_vn:
            f.write('vn %f %f %f\n' % (n[0], n[1], n[2]))
        for name, faces in out_f:
            f.write('usemtl %s\n' % name)
            for face in faces:
                refs = []
                for v, t, n in face:
                    if out_vt and out_vn:
                        refs.append('%d/%d/%d' % (v, t, n))
                    elif out_vn:
                        refs.append('%d//%d' % (v, n))
                    else:
                        refs.append('%d' % v)
                f.write('f %s\n' % ' '.join(refs))

    with open(mtl_path, 'w') as f:
        for name, (r, g, b) in mats.items():
            f.write('newmtl %s\nKd %f %f %f\nKa 0 0 0\nKs 0.1 0.1 0.1\n\n' % (name, r, g, b))

    print('verts=%d faces=%d materials=%d' %
          (len(out_v), sum(len(fl) for _, fl in out_f), len(mats)))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
