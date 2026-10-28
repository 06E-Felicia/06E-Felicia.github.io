"""Render actual Vacation fields into AI-readable PNG/MP4 evidence and an offline player."""
import argparse
import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

# Optional user-local dependencies; the repository never mutates the bundled runtime.
extra = Path(os.environ.get('VACATION_REPLAY_DEPS', str(Path.home() / '.cache/vacation-replay/python')))
if extra.is_dir():
    sys.path.insert(0, str(extra))
if Path('/tmp/vacation-replay-tools').is_dir():
    sys.path.insert(0, '/tmp/vacation-replay-tools')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.collections import LineCollection
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg
from vacation_replay_data import load_manifest, read_frame, local_file

ROOT = Path(__file__).resolve().parents[2]
RADAR = LinearSegmentedColormap.from_list('radar', ['#284da0', '#27afdf', '#30ba6e', '#e7dc43', '#f37829', '#ce3155', '#d395ee'])
WIND = LinearSegmentedColormap.from_list('wind', ['#22355b', '#346aa0', '#42aea8', '#9dcc7b', '#f0b95c', '#df6464'])
RAIN = LinearSegmentedColormap.from_list('rainfall', ['#fffefd', '#d8ebf6', '#7cbeb9', '#9ac66e', '#e4cd68', '#ee945b', '#d95b7d', '#80518a'])
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.edgecolor': '#afb4c3', 'axes.labelcolor': '#4f5266', 'text.color': '#353149', 'figure.facecolor': '#fbfaff'})


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')


def stamp(manifest, seconds):
    minutes = round(seconds / 60) + manifest['config']['startHour'] * 60
    return f'Day {minutes // 1440 + 1} {minutes // 60 % 24:02}:{minutes % 60:02} UTC+8 | +{seconds / 3600:.2f} h'


def extent(grid):
    return [-grid['width'] / 2000, grid['width'] / 2000, -grid['height'] / 2000, grid['height'] / 2000]


def render(directory, publish=True):
    directory = Path(directory).resolve()
    manifest = load_manifest(directory)
    report = json.loads((directory / 'report.json').read_text())
    for spec in manifest['source'].values():
        if hashlib.sha256(local_file(directory, spec['path']).read_bytes()).hexdigest() != spec['sha256']:
            raise ValueError('Archived source was changed')
    images = directory / 'images'
    images.mkdir(exist_ok=True)
    geometry = json.loads((directory / 'terrain-fields.json').read_text())
    terrain_raw = gzip.decompress((directory / 'terrain-fields.bin.gz').read_bytes())
    spec = geometry['fields']['land']
    land = np.frombuffer(terrain_raw, dtype='<f4', count=geometry['grid']['nx'] * geometry['grid']['ny'], offset=spec['offset']).reshape(geometry['grid']['ny'], geometry['grid']['nx'])
    coast = json.loads((directory / 'coastlines.json').read_text())['coordinates']
    segments = [np.asarray(line) / 1000 for line in coast if len(line) > 1]
    g = manifest['grids']['environment']
    xx = (np.arange(g['nx']) + .5) * g['dx'] / 1000 - g['width'] / 2000
    yy = (np.arange(g['ny']) + .5) * g['dx'] / 1000 - g['height'] / 2000
    fig = plt.figure(figsize=(14.4, 6.4), dpi=100)
    axes = [fig.add_axes([.05, .24, .41, .62]), fig.add_axes([.55, .24, .41, .62])]
    for ax, title in zip(axes, ['Composite radar reflectivity', 'Southwest monsoon: wind speed / direction']):
        ax.imshow(land, origin='lower', extent=extent(g), cmap=LinearSegmentedColormap.from_list('land', ['#e4eef3', '#f3f2ee']), vmin=0, vmax=1)
        ax.add_collection(LineCollection(segments, colors='#7f8b93', linewidths=.5, zorder=4))
        ax.set(xlim=(-g['width']/2000,g['width']/2000), ylim=(-g['height']/2000,g['height']/2000), xlabel='Local east (km)' if manifest['config']['geography']=='idealized' else 'Projected east (km)', ylabel='Local north (km)' if manifest['config']['geography']=='idealized' else 'North from 22.5 N (km)', title=title)
        ax.grid(alpha=.18, linewidth=.5)
    radar = axes[0].imshow(np.zeros((2, 2)), origin='lower', extent=extent(manifest['grids']['radar']), cmap=RADAR, vmin=5, vmax=65, interpolation='nearest', zorder=2)
    wind = axes[1].imshow(np.zeros((2, 2)), origin='lower', extent=extent(g), cmap=WIND, vmin=0, vmax=30, alpha=.8, interpolation='nearest', zorder=2)
    stride = max(1, round(60000 / g['dx']))
    X, Y = np.meshgrid(xx[::stride], yy[::stride])
    arrows = axes[1].quiver(X, Y, np.zeros_like(X), np.zeros_like(Y), color='#30394a', angles='xy', scale_units='xy', scale=.28, width=.003, zorder=5)
    for index, artist in enumerate([radar, wind]):
        bar = fig.colorbar(artist, cax=fig.add_axes([.05 + .5 * index, .12, .41, .022]), orientation='horizontal', extend='max')
        bar.set_label('dBZ' if index == 0 else 'm/s')
    title = fig.text(.5, .955, '', ha='center', fontsize=15, fontweight='bold')
    foot = fig.text(.5, .01, '', ha='center', fontsize=9)
    video = directory / 'replay.mp4'
    encoder = imageio_ffmpeg.write_frames(str(video), (1440, 640), fps=8, codec='libx264', quality=8, pix_fmt_in='rgb24', pix_fmt_out='yuv420p', output_params=['-movflags', '+faststart'])
    encoder.send(None)
    max_residual = 0
    no_cells_rain = []
    source_samples = []
    unit_corrections = 0
    try:
        for entry in manifest['frames']:
            metadata, fields = read_frame(directory, manifest, entry)
            # Metadata-only correction for the initial 1.3 recorder descriptors; numerical arrays stay immutable.
            changed = False
            if manifest['model'] == 'vacation-1.3.0':
                for key, units in {'qcL':'kg/m2','qcM':'kg/m2','tl':'K','tm':'K','um':'m/s','vm':'m/s'}.items():
                    if key in metadata['fields'] and metadata['fields'][key]['units'] != units:
                        metadata['fields'][key]['units'] = units; changed = True; unit_corrections += 1
                if changed:write_json(directory / entry['data'], metadata)
            if 'sourceAccounting' in metadata:source_samples.append(metadata)
            radar.set_data(np.ma.masked_where(~np.isfinite(fields['reflectivity_composite']) | (fields['reflectivity_composite'] < 5), fields['reflectivity_composite']))
            speed = np.hypot(fields['u'], fields['v'])
            wind.set_data(speed)
            arrows.set_UVC(fields['u'][::stride, ::stride], fields['v'][::stride, ::stride])
            title.set_text(f'Vacation warm-sector simulation | {stamp(manifest, entry["simTime"])}')
            metrics = entry['metrics']
            foot.set_text(f'Active cells: {metrics["cells"]} | sampled max rain: {metrics["maxRate"]:.1f} mm/h | max accumulation: {metrics["maxTotal"]:.1f} mm | seed {manifest["config"]["seed"]} | synthetic, not observed')
            fig.canvas.draw()
            rgba = np.asarray(fig.canvas.buffer_rgba())
            rgb = np.ascontiguousarray(rgba[:, :, :3])
            Image.fromarray(rgb).save(directory / entry['image'], optimize=False)
            entry['imageSha256'] = hashlib.sha256((directory / entry['image']).read_bytes()).hexdigest()
            entry['metadataSha256'] = hashlib.sha256((directory / entry['data']).read_bytes()).hexdigest()
            encoder.send(rgb.tobytes())
            max_residual = max(max_residual, metrics['relativeResidual'])
            if metrics['cells'] == 0 and metrics['maxRate'] >= 10:
                no_cells_rain.append({'simTime': entry['simTime'], 'maxRate': metrics['maxRate']})
            if entry['index'] % 48 == 0:
                print(json.dumps({'rendered': entry['index'] + 1, 'total': len(manifest['frames'])}), flush=True)
    finally:
        encoder.close()
        plt.close(fig)
    # Uniform temporal contact sheets, with no selection by visually favorable conditions.
    sheets = []
    font = ImageFont.truetype(str(Path(matplotlib.get_data_path()) / 'fonts/ttf/DejaVuSans.ttf'), 15)
    for day in range(math.ceil(manifest['config']['hours'] / 24)):
        selected = []
        for hour in np.arange(day * 24, min((day + 1) * 24, manifest['config']['hours']) + .001, 2):
            selected.append(min(manifest['frames'], key=lambda f: abs(f['simTime'] - hour * 3600)))
        columns, cell_w, cell_h = 4, 400, 325
        sheet = Image.new('RGB', (columns * cell_w, math.ceil(len(selected) / columns) * cell_h + 45), '#fbfaff')
        draw = ImageDraw.Draw(sheet)
        draw.text((15, 12), f'Radar contact sheet | simulation hours {day * 24} - {min((day + 1) * 24, manifest["config"]["hours"])} | fixed dBZ scale 5-65', fill='#353149', font=font)
        for i, entry in enumerate(selected):
            thumb = Image.open(directory / entry['image']).crop((65, 75, 670, 545)).resize((390, 290))
            x, y = (i % columns) * cell_w + 5, (i // columns) * cell_h + 45
            sheet.paste(thumb, (x, y))
            draw.text((x + 5, y + 292), stamp(manifest, entry['simTime']), fill='#353149', font=font)
        name = f'contact-day-{day + 1}.png'
        sheet.save(directory / name)
        sheets.append(name)
    # Final rainfall is the original 1 km ledger, not a rendering of radar colors.
    raw = (directory / report['rainfall']['oneKmData']['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != report['rainfall']['oneKmData']['sha256']:
        raise ValueError('Rainfall ledger checksum mismatch')
    rg = manifest['grids']['rainLedger']
    rainfall = np.frombuffer(gzip.decompress(raw), dtype='<f4').reshape(rg['ny'], rg['nx'])
    fig, ax = plt.subplots(figsize=(11, 8), dpi=140)
    artist = ax.imshow(rainfall, origin='lower', extent=extent(rg), cmap=RAIN, vmin=0, vmax=500, interpolation='nearest')
    ax.add_collection(LineCollection(segments, colors='#53616b', linewidths=.5))
    ax.set(title=f'Total rainfall, +{manifest["config"]["hours"]} h | native 1 km ledger | maximum {float(rainfall.max()):.1f} mm', xlabel='Local east (km)' if manifest['config']['geography']=='idealized' else 'Projected east (km)', ylabel='Local north (km)' if manifest['config']['geography']=='idealized' else 'North from 22.5 N (km)')
    ax.set_xlim(-rg['width']/2000,rg['width']/2000);ax.set_ylim(-rg['height']/2000,rg['height']/2000)
    fig.colorbar(artist, ax=ax, label='mm; fixed cross-process range 0-500', extend='max')
    fig.tight_layout();fig.savefig(directory / 'rainfall-total.png');plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,8),dpi=140)
    artist=ax.imshow(rainfall,origin='lower',extent=extent(rg),cmap=RAIN,vmin=0,vmax=120,interpolation='nearest')
    ax.add_collection(LineCollection(segments,colors='#53616b',linewidths=.5))
    ax.set_xlim(-rg['width']/2000,rg['width']/2000);ax.set_ylim(-rg['height']/2000,rg['height']/2000)
    ax.set(title='Diagnostic total rainfall | FIXED 0-120 mm scale | native ledger, unchanged data',xlabel='Local east (km)',ylabel='Local north (km)')
    fig.colorbar(artist,ax=ax,label='mm; fixed diagnostic range 0-120',extend='max');fig.tight_layout();fig.savefig(directory/'rainfall-diagnostic-0-120.png');plt.close(fig)
    hours = [f['simTime'] / 3600 for f in manifest['frames']]
    fig, axes = plt.subplots(4, 1, figsize=(12, 10), dpi=120, sharex=True)
    axes[0].plot(hours, [f['metrics']['maxRate'] for f in manifest['frames']], color='#aa527e');axes[0].set_ylabel('Sampled max rain\n(mm/h)')
    axes[1].plot(hours, [100 * f['metrics']['area40Km2'] / (g['width']*g['height']/1e6) for f in manifest['frames']], color='#3e7385');axes[1].set_ylabel('Area >=40 dBZ\n(% of domain)')
    axes[2].plot(hours, [f['metrics']['cells'] for f in manifest['frames']], color='#7863b6');axes[2].set_ylabel('Active cells')
    axes[3].semilogy(hours, [max(1e-16, f['metrics']['relativeResidual']) for f in manifest['frames']], color='#516e5d');axes[3].axhline(1e-6, ls='--', color='#aa527e');axes[3].set_ylabel('Relative water\nbudget residual');axes[3].set_xlabel('Simulation hour')
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle(f'Actual process diagnostics | sampled every {manifest["frameIntervalSeconds"] / 60:g} simulation minutes; not interval averages')
    fig.tight_layout();fig.savefig(directory / 'process-diagnostics.png');plt.close(fig)
    if source_samples:
        fig, axs = plt.subplots(3, 1, figsize=(12, 9), dpi=120, sharex=True)
        sh = [m['simTime']/3600 for m in source_samples]
        for key,label in [('environmentCondensed','nonprecipitating environmental cloud'),('cellCondensed','activated cell condensation')]:
            axs[0].plot(sh,[m['stats']['sources'].get(key,0)/1e9 for m in source_samples],label=label)
        for key,label in [('coreGround','core origin'),('detrainedGround','detrained origin')]:
            axs[1].plot(sh,[m['stats']['sources'].get(key,0)/1e9 for m in source_samples],label=label)
        for key in ['core','detrained']:
            axs[2].semilogy(sh,[max(1e-16,abs(m['sourceAccounting'][key]['residual'])/max(1,m['sourceAccounting'][key]['in'])) for m in source_samples],label=key)
        axs[0].set_ylabel('Cumulative condensation (10^9 kg)');axs[1].set_ylabel('Cumulative ground rain (10^9 kg)');axs[2].set_ylabel('Source budget relative residual');axs[2].set_xlabel('Simulation hour')
        for ax in axs:ax.grid(alpha=.2);ax.legend()
        fig.suptitle('Process-source accounting; environmental cloud has no direct rain channel')
        fig.tight_layout();fig.savefig(directory/'source-accounting.png');plt.close(fig)
        manifest['sourceAccountingVisual']='source-accounting.png'
    if unit_corrections:manifest['metadataUnitCorrections']={'count':unit_corrections,'reason':'Initial 1.3 descriptors corrected to kg/m2, K and m/s before metadata verification; raw arrays unchanged.'}
    diagnostics = {'frames': len(manifest['frames']), 'maximumSampledWaterResidual': max_residual, 'framesWithNoActiveCellsAndRainAbove10MmH': no_cells_rain, 'importantLimits': manifest['limitations'], 'reviewStatus': 'not yet compared with observed radar or papers'}
    write_json(directory / 'diagnostics.json', diagnostics)
    # The browser receives an immutable image sequence; it cannot accidentally rerun physics.
    manifest['renderStatus'] = 'complete'
    manifest['verificationStatus'] = 'pending'
    manifest['visuals'] = {'video': 'replay.mp4', 'rainfall': 'rainfall-total.png', 'rainfallDiagnostic':'rainfall-diagnostic-0-120.png', 'diagnostics': 'process-diagnostics.png', 'contacts': sheets}
    manifest['videoSha256'] = hashlib.sha256(video.read_bytes()).hexdigest()
    write_json(directory / 'manifest.json', manifest)
    viewer_assets = directory / 'viewer-assets'
    for relative in ['styles/simulator.css','styles/simulation-v2.css','styles/vacation-replay.css','scripts/vacation-replay.js']:
        target = viewer_assets / relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT / 'assets' / relative,target)
    for relative in ['development/scripts/record_vacation_replay.cjs','development/scripts/render_vacation_replay.py','development/scripts/vacation_replay_data.py','development/scripts/requirements-vacation-replay.txt','development/scripts/verify_vacation_replay.py']:
        source = ROOT / relative
        destination = 'source/' + source.name
        shutil.copyfile(source,directory / destination)
        manifest['source'][relative] = {'path':destination,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    write_json(directory / 'manifest.json',manifest)
    viewer = (ROOT / 'VacationReplay.html').read_text().replace('assets/', 'viewer-assets/').replace('simulation/vacation-replays/latest.js', 'manifest.js').replace('href="Vacation.html"', 'href="../../../Vacation.html"')
    (directory / 'index.html').write_text(viewer)
    from verify_vacation_replay import verify
    verify(directory)
    manifest['verificationStatus'] = 'complete'
    write_json(directory / 'manifest.json',manifest)
    payload = json.dumps(manifest, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    (directory / 'manifest.js').write_text('window.VACATION_REPLAY={manifest:' + payload + ',base:new URL(".",document.currentScript.src).href};\n')
    if publish:
        parent = directory.parent
        if parent != ROOT / 'simulation/vacation-replays':
            raise ValueError('Publishing requires the repository replay folder')
        (parent / 'latest.js').write_text('window.VACATION_REPLAY={manifest:' + payload + ',base:new URL(' + json.dumps(directory.name + '/') + ',document.currentScript.src).href};\n')
        write_json(parent / 'latest.json', {'schema': manifest['schema'], 'status': 'complete', 'directory': directory.name, 'manifestSha256': hashlib.sha256((directory / 'manifest.json').read_bytes()).hexdigest()})
    guide = f'''# AI 回放阅读入口\n\n本轮已完整运行 {manifest['config']['hours']} 小时，共 {report['steps']} 个 {manifest['physicsStepSeconds']} 秒物理步，保存 {len(manifest['frames'])} 帧（含初始和结束时刻）。后台场景参数通过与生产 Worker 相同的生成函数生成；固定归档种子为 {manifest['config']['seed']}，使用 {manifest['config']['quality']} 档；地理类型为 {manifest['config']['geography']}（idealized 为合成地理原型）。\n\n先看 `replay.mp4` 或 `index.html`，再查看 `contact-day-*.png` 的等间隔时序、`rainfall-total.png` 的原始 1 km 累计雨量，以及 `process-diagnostics.png`。每一张 `images/NNNN.png` 对应 `frames/NNNN.json` 和 `.bin.gz`，可使用仓库 `development/scripts/vacation_replay_data.py` 解码；逐帧数据带 SHA-256 校验。\n\n`manifest.json` 给出全部配置、网格、单位、量化规则、投影与归档源码摘要；`report.json` 给出完整运行与水量收支；`births.ndjson` 保留单体触发事件，`stations.csv` 保留站点位置的模型雨量与风。CSV 雨量来自 1 km 账本网格采样，不是观测，也不宣称 1 km 解析精度。\n\n水量相对残差：{report['audit']['relativeResidual']:.6g}；最大累计雨量：{report['rainfall']['maxTotalMm']:.1f} mm。这些只说明运行和数值收支，不说明已与论文或实况一致。\n\n请分别检查回波纹理、强对流核、雨带破碎和组织化、新生/后向传播、准静止和列车效应、降水空间分布、日变化及冷池关系。对照论文时区分观测图与论文模式图，列明图号、时段、分辨率和资料来源。本轮是没有指定历史日期的合成过程；没有配准的观测数据时，不应虚构 CSI/FSS 或相似度百分数。可以做机制与形态比较，并指出缺失资料。\n\n新版归档逐帧保存来源标记的高低层降水水库及脱离云水，元数据 sourceAccounting 包含帧间累计源项和水库收支。环境云不直接降水。不能仅凭零活跃单体时仍下雨判定错误，应检查之前产生的凝结物是否在合理沉降和衰减。\n\n请将本轮验收写到 `DESIGN_ACCEPTANCE.md`，将可执行修改要求写到 `NEXT_REVISION_PLAN.md`，按优先级列问题、证据、代码位置和复验门槛。保留验收结果供用户审阅。\n'''
    (directory / 'AI_REVIEW.md').write_text(guide, encoding='utf8')
    print(json.dumps({'status': 'complete', 'directory': str(directory), 'frames': len(manifest['frames']), 'video': str(video)}), flush=True)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory');parser.add_argument('--no-publish', action='store_true')
    args = parser.parse_args();render(args.directory, publish=not args.no_publish)
