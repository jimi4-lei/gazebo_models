#!/usr/bin/env python3
"""把带 usemtl 分组的 OBJ 按材质拆分成多个单色 OBJ，并生成 MuJoCo XML 片段。

用法: python3 split_obj.py <in.obj> <in.mtl> <out_dir> <prefix>
输出: <out_dir>/<prefix>_NNN.obj (每材质一个, 含顶点色)
      <out_dir>/<prefix>_geoms.xml (可直接粘贴进 <asset>/<worldbody>)
"""
import sys
import os


def parse_mtl(path):
    """mtlname -> rgb"""
    colors = {}
    name = None
    with open(path) as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == 'newmtl':
                name = parts[1]
            elif parts[0] == 'Kd' and name:
                colors[name] = tuple(float(x) for x in parts[1:4])
    return colors


def main(in_obj, in_mtl, out_dir, prefix):
    colors = parse_mtl(in_mtl)
    verts = []          # 全部顶点 (坐标+颜色)
    groups = {}         # matname -> [(face tuples)...]
    cur = None
    with open(in_obj) as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == 'v':
                verts.append([float(x) for x in parts[1:7]])
            elif parts[0] == 'usemtl':
                cur = parts[1]
                groups.setdefault(cur, [])
            elif parts[0] == 'f':
                idx = [int(p.split('/')[0]) - 1 for p in parts[1:]]
                groups[cur].append(idx)

    os.makedirs(out_dir, exist_ok=True)
    asset_lines = []
    geom_lines = []
    for i, (mat, faces) in enumerate(sorted(groups.items(), key=lambda kv: -len(kv[1]))):
        fname = '%s_%03d.obj' % (prefix, i)
        used = sorted({vi for face in faces for vi in face})
        remap = {vi: k + 1 for k, vi in enumerate(used)}
        # MuJoCo 编译时对每个 mesh 做凸包, 纯平面会触发 qhull 错误。
        # 视觉专用, 加 1e-4 量级的 z 抖动让网格非退化。
        zs = {verts[vi][2] for vi in used}
        jitter = 1e-4 if len(zs) == 1 else 0.0
        with open(os.path.join(out_dir, fname), 'w') as f:
            for k, vi in enumerate(used):
                v = list(verts[vi])
                if jitter:
                    v[2] += jitter * ((k % 3) - 1)
                f.write('v %s\n' % ' '.join('%g' % x for x in v))
            for face in faces:
                f.write('f %s\n' % ' '.join(str(remap[vi]) for vi in face))
        rgb = colors.get(mat, (0.8, 0.8, 0.8))
        mesh_name = '%s_%03d' % (prefix, i)
        asset_lines.append(
            '    <mesh name="%s" file="%s"/>' % (mesh_name, fname))
        geom_lines.append(
            '      <geom name="%s_v" type="mesh" mesh="%s" rgba="%g %g %g 1" '
            'contype="0" conaffinity="0" group="2"/>' % (mesh_name, mesh_name, *rgb))
        print('%s: %d faces, rgb=%s' % (fname, len(faces), rgb))

    with open(os.path.join(out_dir, prefix + '_geoms.xml'), 'w') as f:
        f.write('<!-- ====== %s 视觉 mesh (按材质拆分) ====== -->\n' % prefix)
        f.write('<!-- 放入 <asset> -->\n')
        f.write('\n'.join(asset_lines))
        f.write('\n\n<!-- 放入 worldbody 的静态 body 内 -->\n')
        f.write('\n'.join(geom_lines))
        f.write('\n')
    print('total %d materials -> %s/' % (len(groups), out_dir))


if __name__ == '__main__':
    main(*sys.argv[1:5])
